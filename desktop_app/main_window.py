"""Thread-safe production desktop window for Video Downloader."""
from __future__ import annotations
import threading
import os
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)
from .models import DownloadEvent, DownloadRequest, DownloadResult
from .queue import DownloadQueue
from .theme import app_font, stylesheet
from .widgets import DownloadCard, QueueList, UrlInput

class WorkerSignals(QObject):
    _event=Signal(object); _finished=Signal(object); _failed=Signal(str)
    def connect_event(self,receiver,connection_type=Qt.AutoConnection): self._event.connect(receiver,connection_type)
    def connect_finished(self,receiver,connection_type=Qt.AutoConnection): self._finished.connect(receiver,connection_type)
    def connect_failed(self,receiver,connection_type=Qt.AutoConnection): self._failed.connect(receiver,connection_type)
    def emit_event(self,event):
        if not isinstance(event,DownloadEvent): raise TypeError("event must be a DownloadEvent")
        self._event.emit(event)
    def emit_finished(self,result):
        if not isinstance(result,DownloadResult): raise TypeError("result must be a DownloadResult")
        self._finished.emit(result)
    def emit_failed(self,error):
        if not isinstance(error,str): raise TypeError("error must be a string")
        self._failed.emit(error)

class WorkerBridge(QObject):
    _event_for_item=Signal(str,object); _finished_for_item=Signal(str,object); _failed_for_item=Signal(str,str)
    def __init__(self,item_id,parent=None): super().__init__(parent); self.item_id=item_id
    def connect_event(self,receiver,connection_type=Qt.AutoConnection): self._event_for_item.connect(receiver,connection_type)
    def connect_finished(self,receiver,connection_type=Qt.AutoConnection): self._finished_for_item.connect(receiver,connection_type)
    def connect_failed(self,receiver,connection_type=Qt.AutoConnection): self._failed_for_item.connect(receiver,connection_type)
    @Slot(object)
    def on_event(self,event):
        if not isinstance(event,DownloadEvent): raise TypeError("event must be a DownloadEvent")
        self._event_for_item.emit(self.item_id,event)
    @Slot(object)
    def on_finished(self,result):
        if not isinstance(result,DownloadResult): raise TypeError("result must be a DownloadResult")
        self._finished_for_item.emit(self.item_id,result)
    @Slot(str)
    def on_failed(self,error): self._failed_for_item.emit(self.item_id,error)

class DownloadWorker(QRunnable):
    def __init__(self,service,request): super().__init__(); self.service=service; self.request=request; self.cancel_event=threading.Event(); self.signals=WorkerSignals()
    @Slot()
    def run(self):
        try:
            result=self.service.download(self.request,self.signals.emit_event,self.cancel_event)
            if not isinstance(result,DownloadResult): result=DownloadResult(bool(result),None,None,None,None)
            self.signals.emit_finished(result)
        except Exception as exc: self.signals.emit_failed(str(exc))

class SettingsDialog(QDialog):
    save_requested = Signal()
    def __init__(self,settings,parent=None):
        super().__init__(parent); self.setObjectName("settingsDialog"); self.setWindowTitle("Settings"); self.setModal(True); self.setMinimumWidth(500)
        root=QVBoxLayout(self); root.setContentsMargins(24,20,24,20); root.setSpacing(12)
        self.general_group=QGroupBox("General",self); general=QFormLayout(self.general_group); general.setSpacing(10)
        output=QWidget(self); output_layout=QHBoxLayout(output); output_layout.setContentsMargins(0,0,0,0); self.output_dir_edit=QLineEdit(str(settings.output_dir),output); self.output_dir_edit.setObjectName("settingsOutputDirectory"); browse=QPushButton("Browse",output); browse.clicked.connect(self._choose_output_dir); output_layout.addWidget(self.output_dir_edit,1); output_layout.addWidget(browse); general.addRow("Output directory",output)
        self.concurrent_downloads_spin=QSpinBox(self); self.concurrent_downloads_spin.setRange(1,8); self.concurrent_downloads_spin.setValue(max(1,int(settings.concurrent_downloads))); self.concurrent_downloads_spin.setObjectName("concurrentDownloads"); general.addRow("Concurrent downloads",self.concurrent_downloads_spin)
        self.startup_behavior_combo=QComboBox(self); self.startup_behavior_combo.setObjectName("startupBehavior"); self.startup_behavior_combo.setAccessibleName("Startup behavior"); self.startup_behavior_combo.addItem("Open normally","normal"); self.startup_behavior_combo.addItem("Start minimized","minimized"); self.startup_behavior_combo.setCurrentIndex(max(0,self.startup_behavior_combo.findData(settings.startup_behavior))); general.addRow("Startup",self.startup_behavior_combo)
        self.theme_combo=QComboBox(self); self.theme_combo.setObjectName("settingsTheme"); self.theme_combo.setAccessibleName("Theme"); self.theme_combo.addItem("Dark","dark"); self.theme_combo.addItem("Light","light"); self.theme_combo.setCurrentIndex(max(0,self.theme_combo.findData(settings.theme))); general.addRow("Theme",self.theme_combo); root.addWidget(self.general_group)
        self.network_group=QGroupBox("Network & access",self); network=QFormLayout(self.network_group); network.setSpacing(10)
        self.proxy_enabled_checkbox=QCheckBox("Use proxy",self); self.proxy_enabled_checkbox.setObjectName("proxyEnabled"); self.proxy_enabled_checkbox.setAccessibleName("Use proxy"); self.proxy_enabled_checkbox.setChecked(bool(settings.use_proxy)); network.addRow("Proxy",self.proxy_enabled_checkbox); self.proxy_url_edit=QLineEdit(settings.proxy_url or "",self); self.proxy_url_edit.setObjectName("proxyUrl"); self.proxy_url_edit.setAccessibleName("Proxy URL"); self.proxy_url_edit.setPlaceholderText("socks5://127.0.0.1:1080"); self.proxy_enabled_checkbox.toggled.connect(self.proxy_url_edit.setEnabled); self.proxy_url_edit.setEnabled(self.proxy_enabled_checkbox.isChecked()); network.addRow("Proxy address",self.proxy_url_edit)
        self.cookie_browser_combo=QComboBox(self); self.cookie_browser_combo.setObjectName("browserCookies"); self.cookie_browser_combo.setAccessibleName("Browser cookies"); [(self.cookie_browser_combo.addItem(label,value)) for label,value in (("None",None),("Chrome","chrome"),("Edge","edge"),("Firefox","firefox"),("Brave","brave"),("Opera","opera"),("Chromium","chromium"))]; self.cookie_browser_combo.setCurrentIndex(max(0,self.cookie_browser_combo.findData(settings.cookie_browser or None))); network.addRow("Browser cookies",self.cookie_browser_combo); root.addWidget(self.network_group)
        self.error_label=QLabel(self); self.error_label.setObjectName("settingsError"); self.error_label.setStyleSheet("color:#F06A75;"); self.error_label.setWordWrap(True); self.error_label.hide(); root.addWidget(self.error_label)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel,self); self.save_button=buttons.button(QDialogButtonBox.Save); self.save_button.setObjectName("settingsSave"); self.save_button.setAccessibleName("Save settings"); self.cancel_button=buttons.button(QDialogButtonBox.Cancel); self.cancel_button.setObjectName("settingsCancel"); self.cancel_button.setAccessibleName("Cancel settings"); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        browse.setObjectName("settingsBrowse"); browse.setAccessibleName("Browse output directory")
    def _choose_output_dir(self):
        chosen=QFileDialog.getExistingDirectory(self,"Choose output directory",self.output_dir_edit.text())
        if chosen: self.output_dir_edit.setText(chosen)
    def _validate(self):
        raw=self.output_dir_edit.text().strip()
        if not raw: self.error_label.setText("Choose an output directory."); self.error_label.show(); return False
        try:
            path=Path(raw)
            if path.exists() and not path.is_dir(): raise OSError("path is not a directory")
            path.mkdir(parents=True, exist_ok=True)
            if not os.access(path, os.W_OK): raise OSError("directory is not writable")
        except OSError as error: self.error_label.setText(f"Output directory is not writable: {error}"); self.error_label.show(); return False
        if self.proxy_enabled_checkbox.isChecked():
            parsed=urlparse(self.proxy_url_edit.text().strip())
            if parsed.scheme not in {"http","https","socks5","socks5h"} or not parsed.netloc:
                self.error_label.setText("Enter a valid proxy URL, such as socks5://127.0.0.1:1080."); self.error_label.show(); return False
        self.error_label.hide(); return True
    def accept(self):
        if self._validate(): self.save_requested.emit()

class MainWindow(QMainWindow):
    PROGRESS_COLUMN=3; STATUS_COLUMN=4
    def __init__(self,settings,service):
        super().__init__(); self.setObjectName("mainWindow"); self.settings=settings; self.service=service; self.queue=DownloadQueue(); self.thread_pool=QThreadPool(self); self.thread_pool.setMaxThreadCount(max(1,int(getattr(settings,"concurrent_downloads",2)))); self._workers={}; self._bridges={}; self._pending_retries={}; self._cards={}; self.setWindowTitle("Video Downloader"); self.setMinimumSize(1000,680); self.setFont(app_font()); self._build_ui(); self.apply_theme(getattr(settings,"theme","dark"))
    def _build_ui(self):
        root=QWidget(self); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        header=QFrame(self); header.setObjectName("appHeader"); header.setFixedHeight(68); h=QHBoxLayout(header); h.setContentsMargins(24,0,24,0); h.setSpacing(12)
        icon_path=Path(__file__).resolve().parents[1]/"assets"/"video-downloader.ico"; mark=QLabel(header); mark.setFixedSize(32,32); mark.setPixmap(QIcon(str(icon_path)).pixmap(28,28)); h.addWidget(mark)
        brand=QVBoxLayout(); brand.setSpacing(0); title=QLabel("Video Downloader",header); title.setFont(app_font(12,700)); self.header_status=QLabel("Ready",header); self.header_status.setObjectName("muted"); brand.addWidget(title); brand.addWidget(self.header_status); h.addLayout(brand); h.addStretch()
        self.theme_combo=QComboBox(header); self.theme_combo.setObjectName("themeToggle"); self.theme_combo.addItem("Dark","dark"); self.theme_combo.addItem("Light","light"); self.theme_combo.setCurrentIndex(max(0,self.theme_combo.findData(getattr(self.settings,"theme","dark")))); self.theme_combo.currentIndexChanged.connect(lambda _: self.apply_theme(self.theme_combo.currentData())); h.addWidget(self.theme_combo)
        self.settings_button=QPushButton("Settings",header); self.settings_button.setObjectName("settingsButton"); self.settings_button.clicked.connect(self._show_settings); h.addWidget(self.settings_button); outer.addWidget(header)
        content=QWidget(root); layout=QVBoxLayout(content); layout.setContentsMargins(32,24,32,24); layout.setSpacing(14); outer.addWidget(content,1)
        heading=QLabel("Download videos",content); heading.setObjectName("pageTitle"); layout.addWidget(heading); sub=QLabel("Paste one or more links, choose a quality, and add them to your queue.",content); sub.setObjectName("muted"); layout.addWidget(sub)
        composer=QFrame(content); composer.setObjectName("composer"); form=QGridLayout(composer); form.setContentsMargins(16,14,16,16); form.setHorizontalSpacing(10); form.setVerticalSpacing(8)
        label=QLabel("Video URLs",composer); label.setObjectName("sectionTitle"); form.addWidget(label,0,0,1,3); self.url_input=UrlInput(composer); self.url_input.setObjectName("urlInput"); self.url_input.setAccessibleName("Video URLs"); self.url_input.setPlaceholderText("Paste one or more video URLs, one per line"); self.url_input.setFixedHeight(76); self.url_input.submit_requested.connect(lambda: self.add_urls(self.url_input.toPlainText())); form.addWidget(self.url_input,1,0,1,3)
        out_label=QLabel("Output folder",composer); out_label.setObjectName("muted"); form.addWidget(out_label,2,0); self.output_dir_edit=QLineEdit(str(self.settings.output_dir),composer); self.output_dir_edit.setObjectName("outputDirectory"); self.output_dir_edit.editingFinished.connect(self._persist_output_dir); form.addWidget(self.output_dir_edit,2,1); browse=QPushButton("Browse",composer); browse.clicked.connect(self._choose_output_dir); form.addWidget(browse,2,2)
        quality_label=QLabel("Quality",composer); quality_label.setObjectName("muted"); form.addWidget(quality_label,3,0); self.format_combo=QComboBox(composer); self.format_combo.setObjectName("qualityCombo"); self.format_combo.addItem("Automatic (best)","bv*+ba/b"); self.format_combo.addItem("Best single file","best"); idx=self.format_combo.findData(self.settings.format_selector); self.format_combo.setCurrentIndex(idx if idx>=0 else 0); form.addWidget(self.format_combo,3,1); self.add_button=QPushButton("Add to queue",composer); self.add_button.setObjectName("addToQueueButton"); self.add_button.setAccessibleName("Add to queue"); self.add_button.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_MediaPlay)); self.add_button.clicked.connect(lambda: self.add_urls(self.url_input.toPlainText())); form.addWidget(self.add_button,3,2); layout.addWidget(composer)
        queue_heading=QHBoxLayout(); qlabel=QLabel("Download queue",content); qlabel.setObjectName("sectionTitle"); queue_heading.addWidget(qlabel); queue_heading.addStretch(); layout.addLayout(queue_heading)
        scroll=QScrollArea(content); scroll.setObjectName("queueScroll"); scroll.setWidgetResizable(True); self.queue_list=QueueList(); self.queue_list.setObjectName("queueList"); scroll.setWidget(self.queue_list); self.queue_table=self.queue_list; layout.addWidget(scroll,1)
        self.empty_state=QWidget(self.queue_list); empty_layout=QVBoxLayout(self.empty_state); empty_layout.setContentsMargins(16,44,16,44); empty_layout.setAlignment(Qt.AlignCenter); empty_title=QLabel("No downloads yet",self.empty_state); empty_title.setFont(app_font(14,600)); empty_title.setAlignment(Qt.AlignCenter); empty_line=QLabel("Your queued videos will appear here.",self.empty_state); empty_line.setObjectName("muted"); empty_line.setAlignment(Qt.AlignCenter); empty_layout.addWidget(empty_title); empty_layout.addWidget(empty_line); self.queue_list.layout.insertWidget(0,self.empty_state)
        activity=QHBoxLayout(); self.latest_activity=QLabel("No recent activity",content); self.latest_activity.setObjectName("latestActivity"); activity.addWidget(self.latest_activity,1); self.activity_toggle=QPushButton("View activity",content); self.activity_toggle.setObjectName("activityToggle"); self.activity_toggle.setAccessibleName("View activity"); self.activity_toggle.clicked.connect(self._toggle_activity); activity.addWidget(self.activity_toggle); layout.addLayout(activity)
        self.activity_drawer=QFrame(content); self.activity_drawer.setObjectName("activityDrawer"); self.activity_drawer.setAccessibleName("Activity drawer"); drawer_layout=QVBoxLayout(self.activity_drawer); drawer_head=QHBoxLayout(); drawer_head.addWidget(QLabel("Activity",self.activity_drawer)); drawer_head.addStretch(); self.activity_clear=QPushButton("Clear",self.activity_drawer); self.activity_clear.setObjectName("activityClear"); self.activity_clear.setAccessibleName("Clear activity"); self.activity_clear.clicked.connect(lambda: self.activity_log.clear()); drawer_head.addWidget(self.activity_clear); drawer_layout.addLayout(drawer_head); self.activity_log=QPlainTextEdit(self.activity_drawer); self.activity_log.setReadOnly(True); self.activity_log.setObjectName("activityLog"); self.activity_log.setFixedHeight(100); drawer_layout.addWidget(self.activity_log); self.activity_drawer.setVisible(False); layout.addWidget(self.activity_drawer)
    def apply_theme(self,mode):
        mode=mode if mode in ("dark","light") else "dark"; self.settings.theme=mode; self.setStyleSheet(stylesheet(mode))
    def _toggle_activity(self): self.activity_drawer.setVisible(not self.activity_drawer.isVisible()); self.activity_toggle.setText("Hide activity" if self.activity_drawer.isVisible() else "View activity")
    @Slot(str)
    def add_urls(self,text):
        lines=[line.strip() for line in (text or "").splitlines() if line.strip()]
        if not lines:return
        for url in lines:
            request=DownloadRequest(url,Path(self.settings.output_dir),self.format_combo.currentData(),getattr(self.settings,"use_proxy",False),getattr(self.settings,"proxy_url",None),getattr(self.settings,"cookie_browser",None)); item_id=self.queue.add(request); self._add_row(item_id,request)
        self.url_input.clear()
    def _add_row(self,item_id,request):
        card=DownloadCard(item_id,request.url,request.format_selector,self.queue_list); card.action_requested.connect(self._card_action); self._cards[item_id]=card; self.queue_list.add_card(card); self.empty_state.setVisible(False); self._update_header()
    def _card_action(self,item_id,action):
        {"start":self.start_item,"retry":self.retry_item,"cancel":self.cancel_item,"open":self._open_folder,"remove":self.remove_item}.get(action,lambda _:None)(item_id)
    @staticmethod
    def _site(url): return urlparse(url).netloc or "—"
    def _set_status(self,item_id,status):
        card=self._cards.get(item_id)
        if card:
            snap=next((i for i in self.queue.snapshot() if i["id"]==item_id),{}); card.set_status(status,snap.get("percent"),snap.get("speed"),snap.get("eta")); self._update_header()
    @Slot(str)
    def start_item(self,item_id):
        if item_id in self._workers:return
        snapshot=next((i for i in self.queue.snapshot() if i["id"]==item_id),None)
        if not snapshot or snapshot["status"]!="queued":return
        self.queue.update_status(item_id,"running"); self._set_status(item_id,"running"); item=self.queue.get(item_id); worker=DownloadWorker(self.service,item.request); bridge=WorkerBridge(item_id,self); self._workers[item_id]=worker; self._bridges[item_id]=bridge; worker.signals.connect_event(bridge.on_event,Qt.QueuedConnection); worker.signals.connect_finished(bridge.on_finished,Qt.QueuedConnection); worker.signals.connect_failed(bridge.on_failed,Qt.QueuedConnection); bridge.connect_event(self._handle_event,Qt.QueuedConnection); bridge.connect_finished(self._handle_finished,Qt.QueuedConnection); bridge.connect_failed(self._handle_failed,Qt.QueuedConnection); self.thread_pool.start(worker)
    @Slot(str)
    def cancel_item(self,item_id):
        worker=self._workers.get(item_id)
        if worker:worker.cancel_event.set()
        try:self.queue.cancel(item_id)
        except ValueError:return
        self._set_status(item_id,"cancelled"); self._log("Download cancelled")
    @Slot(str)
    def retry_item(self,item_id):
        try:self.queue.retry(item_id)
        except ValueError:return
        previous=self.queue.get(item_id).request; fmt=self.format_combo.currentData() or self.settings.format_selector; self.settings.format_selector=fmt; request=DownloadRequest(previous.url,Path(self.settings.output_dir),fmt,self.settings.use_proxy,self.settings.proxy_url,self.settings.cookie_browser,previous.output_template); self.queue.replace_request(item_id,request); self._set_status(item_id,"queued")
        if item_id in self._workers:self._pending_retries[item_id]=request; self._set_status(item_id,"cancelling"); self._log("Waiting for cancelled download to stop before retrying"); return
        self.start_item(item_id)
    @Slot(str)
    def remove_item(self,item_id):
        if item_id in self._workers:return
        try:self.queue.remove(item_id)
        except KeyError:return
        card=self._cards.pop(item_id,None)
        if card:self.queue_list.remove_card(card)
        self.empty_state.setVisible(not self._cards); self._update_header()
    @Slot(str,object)
    def _handle_event(self,item_id,event):
        sender=self.sender()
        if sender is not None and sender is not self._bridges.get(item_id): return
        if not isinstance(event,DownloadEvent) or item_id in self._pending_retries:return
        current=next((i for i in self.queue.snapshot() if i["id"]==item_id),None)
        if current is None or current["status"]=="cancelled":return
        if event.kind=="metadata":self.queue.update_status(item_id,"running",title=event.title); self._cards[item_id].title_label.setText(event.title or current["url"])
        elif event.kind=="progress":self.queue.update_status(item_id,"running",percent=event.percent,speed=event.speed,eta=event.eta); self._set_status(item_id,"running")
        elif event.kind in ("log","failed","cancelled"):self._log(event.message)
        if event.kind=="failed":self._mark_failed(item_id,event.message,event.error_code)
        elif event.kind=="cancelled":self._mark_cancelled(item_id)
    @Slot(str,object)
    def _handle_finished(self,item_id,result):
        sender=self.sender()
        if sender is not None and sender is not self._bridges.get(item_id): return
        self._workers.pop(item_id,None); self._bridges.pop(item_id,None)
        if self._start_pending_retry(item_id):return
        current=next((i for i in self.queue.snapshot() if i["id"]==item_id),None)
        if current is None or current["status"]=="cancelled":return
        if result.success:self.queue.update_status(item_id,"success",filename=result.filename,title=result.title); self._set_status(item_id,"success"); self._log(f"Finished: {result.title or result.filename or 'download'}")
        else:self._mark_cancelled(item_id) if result.error_code=="cancelled" else self._mark_failed(item_id,result.error_message or "Download failed",result.error_code)
    @Slot(str,str)
    def _handle_failed(self,item_id,error):
        sender=self.sender()
        if sender is not None and sender is not self._bridges.get(item_id): return
        self._workers.pop(item_id,None); self._bridges.pop(item_id,None)
        if self._start_pending_retry(item_id):return
        self._mark_failed(item_id,error,"download_failed")
    def _start_pending_retry(self,item_id):
        if self._pending_retries.pop(item_id,None) is None:return False
        self._set_status(item_id,"queued"); self.start_item(item_id); return True
    def _mark_failed(self,item_id,message,code):
        try:self.queue.update_status(item_id,"failed",error=message,error_code=code)
        except ValueError:return
        self._set_status(item_id,"failed"); self._log(message)
    def _mark_cancelled(self,item_id):
        self._workers.pop(item_id,None); self._set_status(item_id,"cancelled")
        try:self.queue.update_status(item_id,"cancelled")
        except ValueError:pass
    def _log(self,message):
        if message:self.activity_log.appendPlainText(str(message)); self.latest_activity.setText(str(message)); self._update_header()
    def _update_header(self):
        running=sum(1 for i in self.queue.snapshot() if i["status"]=="running"); total=len(self.queue.snapshot()); self.header_status.setText(f"{running} active  ·  {total} queued" if total else "Ready")
    def _persist_output_dir(self):
        selected=self.output_dir_edit.text().strip()
        if not selected:self.output_dir_edit.setText(str(self.settings.output_dir)); return
        self.settings.output_dir=Path(selected)
        try:self.settings.save()
        except OSError as error:self._log(f"Could not save output directory: {error}")
    def _choose_output_dir(self):
        chosen=QFileDialog.getExistingDirectory(self,"Choose output directory",self.output_dir_edit.text())
        if chosen:self.output_dir_edit.setText(chosen); self._persist_output_dir()
    def _open_folder(self,item_id):
        snap=next((i for i in self.queue.snapshot() if i["id"]==item_id),None)
        if snap:QDesktopServices.openUrl(QUrl.fromLocalFile(snap["output_dir"]))
    def _show_settings(self):self._create_settings_dialog().exec()
    def _create_settings_dialog(self):
        dialog=SettingsDialog(self.settings,self); dialog.save_requested.connect(lambda:self._apply_settings_dialog(dialog)); return dialog
    def _apply_settings_dialog(self,dialog):
        output=dialog.output_dir_edit.text().strip()
        if output:self.settings.output_dir=Path(output)
        self.settings.use_proxy=dialog.proxy_enabled_checkbox.isChecked(); self.settings.proxy_url=dialog.proxy_url_edit.text().strip() or None; self.settings.cookie_browser=dialog.cookie_browser_combo.currentData(); self.settings.concurrent_downloads=dialog.concurrent_downloads_spin.value(); self.settings.startup_behavior=dialog.startup_behavior_combo.currentData(); self.settings.theme=dialog.theme_combo.currentData()
        try: self.settings.save()
        except OSError as error: dialog.error_label.setText(f"Could not save settings: {error}"); dialog.error_label.show(); return False
        self.thread_pool.setMaxThreadCount(self.settings.concurrent_downloads); self.output_dir_edit.setText(str(self.settings.output_dir)); self.theme_combo.blockSignals(True); self.theme_combo.setCurrentIndex(max(0,self.theme_combo.findData(self.settings.theme))); self.theme_combo.blockSignals(False); self.apply_theme(self.settings.theme)
        dialog.done(QDialog.Accepted)
        return True
