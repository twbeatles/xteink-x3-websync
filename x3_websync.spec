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
        'lxml', 'ebooklib', 'bs4', 'requests',
        'websync', 'websync.core', 'websync.config', 'websync.config.exceptions', 'websync.config.validator', 'websync.db',
        'websync.scrapers', 'websync.scrapers.css', 'websync.scrapers.rss',
        'websync.scrapers.naver', 'websync.scrapers.naver_common', 'websync.scrapers.naver_cafe', 'websync.scrapers.naver_post',
        'websync.scrapers.tistory', 'websync.scrapers.brunch',
        'websync.scrapers.youtube', 'websync.scrapers.substack',
        'websync.epub', 'websync.upload', 'websync.pipeline',
        'websync.integrations', 'websync.scheduler', 'websync.servers',
        'websync.watch', 'websync.gui',
        'websync.gui.widgets', 'websync.gui.tab_sync', 'websync.gui.tab_calibre',
        'websync.gui.tab_history', 'websync.gui.tab_settings', 'websync.gui.bottom_bar',
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
