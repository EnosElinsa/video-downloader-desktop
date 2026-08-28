[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$')]
    [string]$Version,

    [string]$FFmpegPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$buildRoot = Join-Path $repoRoot "build"
$distRoot = Join-Path $repoRoot "dist"
$testTempRoot = Join-Path $repoRoot ".test-tmp/packaging-temp"
$specPath = Join-Path $PSScriptRoot "video_downloader.spec"
$artifactBase = "VideoDownloader-windows-x64"
$oneFolder = Join-Path $distRoot $artifactBase
$zipPath = Join-Path $distRoot "VideoDownloader-windows-x64.zip"
$oneFile = Join-Path $distRoot "VideoDownloader-windows-x64.exe"
$checksumPath = Join-Path $distRoot "SHA256SUMS.txt"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$buildChecksPath = Join-Path $PSScriptRoot "build_checks.py"

function Assert-ChildPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = [System.IO.Path]::GetFullPath($Path)
    $prefix = $repoRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the repository: $resolved"
    }
    return $resolved
}

function Assert-ExitCode {
    param([Parameter(Mandatory = $true)][string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Validating Windows x64 release environment..."
$envCheck = @"
import platform, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(r'$PSScriptRoot').resolve()))
from build_checks import validate_release_environment
import PyInstaller
validate_release_environment(machine=platform.machine(), pointer_bits=struct.calcsize('P') * 8,
                             python_version=(sys.version_info.major, sys.version_info.minor),
                             pyinstaller_version=PyInstaller.__version__)
"@
python -c $envCheck
Assert-ExitCode "Windows x64 release environment validation"

function Resolve-FFmpegExecutable {
    param([string]$RequestedPath)

    if ($RequestedPath) {
        $candidate = [System.IO.Path]::GetFullPath($RequestedPath)
        if ([System.IO.Directory]::Exists($candidate)) {
            $candidate = Join-Path $candidate "ffmpeg.exe"
        }
        if (-not [System.IO.File]::Exists($candidate)) {
            throw "-FFmpegPath does not resolve to ffmpeg.exe: $candidate"
        }
        return $candidate
    }

    $command = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if ($command -and [System.IO.File]::Exists($command.Source)) {
        return [System.IO.Path]::GetFullPath($command.Source)
    }

    # FFmpeg lists Gyan's Windows builds on its official download page. Pinning
    # both the release and digest makes automated public-release builds repeatable.
    $archiveUrl = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip"
    $checksumUrl = "$archiveUrl.sha256"
    $pinnedSha256 = "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"
    $vendorRoot = Join-Path $buildRoot "vendor/ffmpeg"
    $archivePath = Join-Path $vendorRoot "ffmpeg-8.1.2-essentials_build.zip"
    $vendorChecksumPath = Join-Path $vendorRoot "ffmpeg-8.1.2-essentials_build.zip.sha256"
    $expandedPath = Join-Path $vendorRoot "expanded"
    New-Item -ItemType Directory -Force -Path $vendorRoot | Out-Null

    Write-Host "Downloading pinned FFmpeg 8.1.2 essentials build..."
    Invoke-WebRequest -Uri $checksumUrl -OutFile $vendorChecksumPath
    $publishedSha256 = (Get-Content -Raw $vendorChecksumPath).Trim().Split()[0].ToLowerInvariant()
    if ($publishedSha256 -ne $pinnedSha256) {
        throw "Pinned FFmpeg checksum no longer matches the vendor checksum."
    }
    Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath
    $actualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $pinnedSha256) {
        throw "FFmpeg archive checksum mismatch: expected $pinnedSha256, got $actualSha256"
    }

    Expand-Archive -LiteralPath $archivePath -DestinationPath $expandedPath -Force
    $matches = @(Get-ChildItem -LiteralPath $expandedPath -Filter "ffmpeg.exe" -File -Recurse)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one ffmpeg.exe in the verified archive, found $($matches.Count)."
    }
    return $matches[0].FullName
}

function New-DeterministicZip {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDirectory,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    Add-Type -AssemblyName System.IO.Compression
    $source = [System.IO.Path]::GetFullPath($SourceDirectory)
    $destinationPath = [System.IO.Path]::GetFullPath($Destination)
    $stream = [System.IO.File]::Open($destinationPath, [System.IO.FileMode]::Create)
    $archive = [System.IO.Compression.ZipArchive]::new(
        $stream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $false
    )
    $fixedTimestamp = [System.DateTimeOffset]::new(2000, 1, 1, 0, 0, 0, [System.TimeSpan]::Zero)
    try {
        $files = Get-ChildItem -LiteralPath $source -File -Recurse |
            Sort-Object { [System.IO.Path]::GetRelativePath($source, $_.FullName) }
        foreach ($file in $files) {
            $relative = [System.IO.Path]::GetRelativePath($source, $file.FullName).Replace('\', '/')
            $entryName = "$([System.IO.Path]::GetFileName($source))/$relative"
            $entry = $archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
            $entry.LastWriteTime = $fixedTimestamp
            $input = [System.IO.File]::OpenRead($file.FullName)
            $output = $entry.Open()
            try {
                $input.CopyTo($output)
            }
            finally {
                $output.Dispose()
                $input.Dispose()
            }
        }
    }
    finally {
        $archive.Dispose()
        $stream.Dispose()
    }
}

$buildRoot = Assert-ChildPath $buildRoot
$distRoot = Assert-ChildPath $distRoot
$testTempRoot = Assert-ChildPath $testTempRoot
$localTemp = Join-Path $testTempRoot ("run-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $localTemp | Out-Null
$env:TEMP = $localTemp
$env:TMP = $localTemp
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QPA_FONTDIR = "C:\Windows\Fonts"
$env:PYTHONHASHSEED = "0"
$env:SOURCE_DATE_EPOCH = "946684800"
$requestedFFmpeg = if ($FFmpegPath) { Resolve-FFmpegExecutable $FFmpegPath } else { $null }
if ($requestedFFmpeg) {
    $buildPrefix = $buildRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $distPrefix = $distRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if ($requestedFFmpeg.StartsWith($buildPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        $requestedFFmpeg.StartsWith($distPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        $stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("video-downloader-ffmpeg-" + [Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null
        Copy-Item -LiteralPath $requestedFFmpeg -Destination (Join-Path $stagingRoot "ffmpeg.exe")
        $siblingFFprobe = Join-Path (Split-Path $requestedFFmpeg -Parent) "ffprobe.exe"
        if (Test-Path -LiteralPath $siblingFFprobe -PathType Leaf) {
            Copy-Item -LiteralPath $siblingFFprobe -Destination (Join-Path $stagingRoot "ffprobe.exe")
        }
        $requestedFFmpeg = Join-Path $stagingRoot "ffmpeg.exe"
    }
}
foreach ($target in @($buildRoot, $distRoot)) {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
New-Item -ItemType Directory -Force -Path $buildRoot, $distRoot | Out-Null

Write-Host "Running release test gate..."
python -m pytest -q -p no:cacheprovider
Assert-ExitCode "pytest"
python -c "import PyInstaller; print(PyInstaller.__version__)" | Out-Host
Assert-ExitCode "PyInstaller availability check"

$resolvedFFmpeg = if ($requestedFFmpeg) { $requestedFFmpeg } else { Resolve-FFmpegExecutable $FFmpegPath }
& $resolvedFFmpeg -version | Select-Object -First 1 | Out-Host
Assert-ExitCode "FFmpeg validation"

$generatedDir = Join-Path $buildRoot "generated"
New-Item -ItemType Directory -Force -Path $generatedDir | Out-Null
$versionModule = Join-Path $generatedDir "video_downloader_build_version.py"
[System.IO.File]::WriteAllText($versionModule, "VERSION = `"$Version`"`n", $utf8NoBom)

$env:VIDEO_DOWNLOADER_GENERATED_DIR = $generatedDir
$env:VIDEO_DOWNLOADER_FFMPEG_PATH = $resolvedFFmpeg
$ffmpegDocs = @"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(r'$PSScriptRoot').resolve()))
from build_checks import find_optional_ffmpeg_document
for name in ('LICENSE', 'README.txt'):
    found = find_optional_ffmpeg_document(r'$resolvedFFmpeg', (name,))
    print(f'{name}={found or ""}')
"@
foreach ($line in (python -c $ffmpegDocs)) {
    if ($line -match '^LICENSE=(.+)$') { $env:VIDEO_DOWNLOADER_FFMPEG_LICENSE = $Matches[1] }
    if ($line -match '^README\.txt=(.+)$') { $env:VIDEO_DOWNLOADER_FFMPEG_README = $Matches[1] }
}

Write-Host "Building one-folder artifact..."
$env:VIDEO_DOWNLOADER_BUILD_MODE = "onedir"
python -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath (Join-Path $buildRoot "pyinstaller-onedir") $specPath
Assert-ExitCode "PyInstaller one-folder build"

Write-Host "Building one-file artifact..."
$env:VIDEO_DOWNLOADER_BUILD_MODE = "onefile"
python -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath (Join-Path $buildRoot "pyinstaller-onefile") $specPath
Assert-ExitCode "PyInstaller one-file build"

if (-not (Test-Path -LiteralPath $oneFolder -PathType Container)) {
    throw "Missing one-folder artifact: $oneFolder"
}
if (-not (Test-Path -LiteralPath $oneFile -PathType Leaf)) {
    throw "Missing one-file artifact: $oneFile"
}

New-DeterministicZip -SourceDirectory $oneFolder -Destination $zipPath
python (Join-Path $PSScriptRoot "smoke_test.py") --exe (Join-Path $oneFolder "$artifactBase.exe") --expected-version $Version
Assert-ExitCode "One-folder smoke test"
python (Join-Path $PSScriptRoot "smoke_test.py") --exe $oneFile --expected-version $Version
Assert-ExitCode "One-file smoke test"

$checksumLines = foreach ($artifact in @($zipPath, $oneFile)) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash.ToLowerInvariant()
    "$hash  $([System.IO.Path]::GetFileName($artifact))"
}
[System.IO.File]::WriteAllLines($checksumPath, $checksumLines, $utf8NoBom)
python -c "from pathlib import Path; import sys; sys.path.insert(0, r'$PSScriptRoot'); from build_checks import parse_sha256_manifest; parse_sha256_manifest(Path(r'$checksumPath').read_text())"
Assert-ExitCode "SHA256SUMS validation"

Write-Host "Release artifacts:"
Get-Item -LiteralPath $oneFolder, $zipPath, $oneFile, $checksumPath |
    Select-Object FullName, Length, LastWriteTimeUtc |
    Format-Table -AutoSize
