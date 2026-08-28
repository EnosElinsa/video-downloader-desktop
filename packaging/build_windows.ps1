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
$specPath = Join-Path $PSScriptRoot "video_downloader.spec"
$artifactBase = "VideoDownloader-windows-x64"
$oneFolder = Join-Path $distRoot $artifactBase
$zipPath = Join-Path $distRoot "VideoDownloader-windows-x64.zip"
$oneFile = Join-Path $distRoot "VideoDownloader-windows-x64.exe"
$checksumPath = Join-Path $distRoot "SHA256SUMS.txt"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

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
foreach ($target in @($buildRoot, $distRoot)) {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
New-Item -ItemType Directory -Force -Path $buildRoot, $distRoot | Out-Null

$localTemp = Join-Path $buildRoot "tmp"
New-Item -ItemType Directory -Force -Path $localTemp | Out-Null
$env:TEMP = $localTemp
$env:TMP = $localTemp
$env:PYTHONHASHSEED = "0"
$env:SOURCE_DATE_EPOCH = "946684800"

Write-Host "Running release test gate..."
python -m pytest -q
Assert-ExitCode "pytest"
python -c "import PyInstaller; print(PyInstaller.__version__)" | Out-Host
Assert-ExitCode "PyInstaller availability check"

$resolvedFFmpeg = Resolve-FFmpegExecutable $FFmpegPath
& $resolvedFFmpeg -version | Select-Object -First 1 | Out-Host
Assert-ExitCode "FFmpeg validation"

$generatedDir = Join-Path $buildRoot "generated"
New-Item -ItemType Directory -Force -Path $generatedDir | Out-Null
$versionModule = Join-Path $generatedDir "video_downloader_build_version.py"
[System.IO.File]::WriteAllText($versionModule, "VERSION = `"$Version`"`n", $utf8NoBom)

$env:VIDEO_DOWNLOADER_GENERATED_DIR = $generatedDir
$env:VIDEO_DOWNLOADER_FFMPEG_PATH = $resolvedFFmpeg
$ffmpegRoot = Split-Path (Split-Path $resolvedFFmpeg -Parent) -Parent
$license = Get-ChildItem -LiteralPath $ffmpegRoot -Filter "LICENSE" -File -Recurse | Select-Object -First 1
$readme = Get-ChildItem -LiteralPath $ffmpegRoot -Filter "README.txt" -File -Recurse | Select-Object -First 1
if ($license) { $env:VIDEO_DOWNLOADER_FFMPEG_LICENSE = $license.FullName }
if ($readme) { $env:VIDEO_DOWNLOADER_FFMPEG_README = $readme.FullName }

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

Write-Host "Release artifacts:"
Get-Item -LiteralPath $oneFolder, $zipPath, $oneFile, $checksumPath |
    Select-Object FullName, Length, LastWriteTimeUtc |
    Format-Table -AutoSize
