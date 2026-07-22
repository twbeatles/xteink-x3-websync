# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# 빌드 용량 경량화를 위해 선택적 의존성 및 무거운 라이브러리를 제외합니다.
excludes = [
    # X3 WebSync의 선택적 기능 의존성 (경량화 빌드를 위해 제외)
    'PIL',
    'pillow',
    'youtube_transcript_api',
    'watchdog',
    'googletrans',
    
    # 불필요하고 용량이 큰 라이브러리들
    'numpy',
    'matplotlib',
    'pandas',
    'scipy',
    'PyQt5',
    'PyQt6',
    'PySide2',
    'PySide6',
    'wx',
    'IPython',
    'notebook',
    'unittest',
    'doctest',
    'pdb'
]

a = Analysis(
    ['x3_websync.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('websync/servers/templates/*.html', 'websync/servers/templates'),
        ('websync/epub/themes/*.css', 'websync/epub/themes'),
    ],
    hiddenimports=[
        'lxml', 'lxml.etree', 'ebooklib', 'bs4', 'requests',
        'websync', 'websync.core', 'websync.core.paths', 'websync.core.logger',
        'websync.core.process_lock', 'websync.core.article', 'websync.core.types',
        'websync.config', 'websync.config.exceptions', 'websync.config.validator',
        'websync.config.manager', 'websync.config.secrets',
        'websync.db', 'websync.db.history',
        'websync.backup', 'websync.backup.service', 'websync.backup.atomic_io', 'websync.backup.format',
        # scrapers (13 types + factory/presets)
        'websync.scrapers', 'websync.scrapers.base', 'websync.scrapers.factory',
        'websync.scrapers.types', 'websync.scrapers.presets', 'websync.scrapers.newsletter_base',
        'websync.scrapers.css', 'websync.scrapers.rss', 'websync.scrapers.velog',
        'websync.scrapers.naver', 'websync.scrapers.naver_common',
        'websync.scrapers.naver_cafe', 'websync.scrapers.naver_post',
        'websync.scrapers.tistory', 'websync.scrapers.brunch', 'websync.scrapers.newneek',
        'websync.scrapers.youtube', 'websync.scrapers.substack',
        'websync.scrapers.soonsal', 'websync.scrapers.moneyletter',
        'websync.epub', 'websync.epub.builder', 'websync.epub.css',
        'websync.epub.cover', 'websync.epub.sanitize',
        'websync.upload', 'websync.upload.host', 'websync.upload.remote_path',
        'websync.upload.sync_epub', 'websync.upload.errors',
        'websync.upload.device_client', 'websync.upload.uploader',
        'websync.pipeline', 'websync.pipeline.service',
        'websync.pipeline.sync_pipeline', 'websync.pipeline.preview',
        'websync.pipeline.selected_sync', 'websync.pipeline.article_keys',
        'websync.pipeline.upload_results',
        'websync.pipeline.log_util', 'websync.pipeline.summarizer',
        'websync.pipeline.translator',
        'websync.integrations', 'websync.integrations.calibre', 'websync.integrations.notifier',
        'websync.scheduler', 'websync.scheduler.manager',
        'websync.servers', 'websync.servers.opds', 'websync.servers.web_dashboard',
        'websync.servers.dashboard', 'websync.servers.dashboard.service',
        'websync.servers.dashboard.handler', 'websync.servers.dashboard.http_server',
        'websync.servers.dashboard.session', 'websync.servers.dashboard.templates_loader',
        'websync.watch', 'websync.watch.calibre',
        'websync.gui', 'websync.gui.widgets', 'websync.gui.bottom_bar',
        'websync.gui.app', 'websync.gui.tab_sync', 'websync.gui.tab_calibre',
        'websync.gui.tab_history', 'websync.gui.tab_settings', 'websync.gui.tab_device_files',
        'websync.gui.sync_tab', 'websync.gui.sync_tab.tab', 'websync.gui.sync_tab.sites',
        'websync.gui.device_files', 'websync.gui.device_files.tab',
        'websync.gui.settings_tab', 'websync.gui.settings_tab.tab',
        'websync.gui.settings_tab.backup_sync',
        'websync.gui.app_core', 'websync.gui.app_core.app',
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='x3_websync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False, # 바이너리 스트립 비활성화 (Windows 환경)
    upx=False,   # UPX 압축 비활성화

    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # GUI 모드 구동 (백그라운드 CLI/GUI 시 콘솔창이 뜨지 않음)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements=None,
)
