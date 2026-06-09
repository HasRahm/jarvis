# App Logo & Identity Vocabulary
> When visual_inspect describes an app's logo or the active window title reveals an app name, use this table.
> The ui_type column determines which automation tools work reliably.
> OCR (screen_ocr) = works for native_win32 and html. FAILS for electron_webgl and opengl.
> Use visual_click + visual_inspect for electron_webgl and opengl apps.

## UI Type Reference
- **html** — Browser-rendered DOM. screen_ocr works. browser_navigate + browser_extract_text work.
- **electron** — Electron app (HTML/JS wrapped). screen_ocr partially works on text areas. hybrid_locate_click works for most elements.
- **electron_webgl** — Electron + WebGL canvas (e.g. Figma). screen_ocr FAILS on canvas. Always use visual_click + visual_inspect.
- **native_win32** — Win32 native UI. screen_ocr works. hybrid_locate_click and UIAutomation work.
- **native_win32 + COM** — Win32 with COM automation. Use win32com.client for programmatic control (faster than GUI).
- **java_swing** — Java Swing (IDEs). screen_ocr works on menus. hybrid_locate_click works partially.
- **opengl** — Full OpenGL canvas (e.g. Blender). OCR FAILS everywhere. visual_click + visual_inspect required.
- **html_embedded** — HTML embedded in native shell (Steam). hybrid approach needed.

| App Name | Logo Visual Description | Process Name (Windows) | UI Type | Critical Automation Notes |
|----------|------------------------|----------------------|---------|--------------------------|
| Figma | Four overlapping circles in red, purple, blue, and green forming a cross/clover shape. "Figma" wordmark in dark text beside it. | Figma.exe | electron_webgl | **Community/canvas is WebGL. screen_ocr returns sidebar text only. Use visual_click + visual_inspect for anything in the canvas. hybrid_locate_click works for left sidebar only (non-canvas).** Focus first: desktop_focus_window("Figma"). |
| Google Chrome | Circular pie-chart-like icon divided into red, green, and yellow thirds with a solid blue circle at the center. | chrome.exe | html | Full DOM accessible. browser_navigate + browser_extract_text work. Address bar: press Ctrl+L to focus and clear. Tab management with Ctrl+T, Ctrl+W. |
| Mozilla Firefox | Orange and red flame wrapping around a blue/purple globe. | firefox.exe | html | Same as Chrome. Address bar: Ctrl+L to focus. |
| Microsoft Edge | Stylized blue wave or swirl — looks like a modern cursive lowercase 'e'. | msedge.exe | html | Same as Chrome. Address bar: Ctrl+L or Alt+D. |
| VS Code | Two blue interlocked abstract square shapes — like puzzle pieces or a geometric chevron. Sometimes shown as a simple angular bracket logo. | Code.exe | electron | Command palette: Ctrl+Shift+P. File explorer: Ctrl+Shift+E. Terminal: Ctrl+` (backtick). Extensions: Ctrl+Shift+X. Search: Ctrl+Shift+F. Most menu actions via keyboard. OCR works on editor text. |
| Cursor (AI IDE) | Similar to VS Code but with a distinct cursor/pointer element. Usually "Cursor" text visible in title bar. | Cursor.exe | electron | Same keyboard shortcuts as VS Code. AI: Ctrl+K (inline edit), Ctrl+L (chat). |
| Slack | Colorful hashtag (#) symbol with four rounded arms/ends — each arm is a different color: red (top-left), yellow (top-right), green (bottom-right), blue (bottom-left). | slack.exe | electron | Message input at bottom. Channel list in left sidebar. Search: Ctrl+K or Ctrl+F. Compose new message: + icon beside Channels. |
| Discord | White stylized game controller / speech bubble hybrid shape on dark purple/dark background. | Discord.exe | electron | Server list on far left edge (icons). Channel list second column. Message input at bottom of chat. Search: Ctrl+K. |
| Notion | Clean black uppercase letter 'N' on white background, OR a stylized stacked notebook/page shape. | Notion.exe | electron | Page tree in left sidebar. Content in main area. "/" to trigger slash commands for blocks. |
| Obsidian | Purple/magenta diamond or crystal shape. | Obsidian.exe | electron | Vault files in left sidebar. Note content in main area. Ctrl+P for command palette. |
| Zoom | Solid blue video camera icon. "Zoom" text label often visible. | Zoom.exe | native_win32 | Join/Start buttons are large and prominent. OCR works on most UI. Meeting controls visible at top or bottom of screen. |
| Microsoft Teams | Purple or blue square with a white letter 'T' icon. | Teams.exe | electron | Chat list on left. Message input at bottom. Calendar, Calls, Files in left navigation. Search: Ctrl+E. |
| Spotify | Green circle with three curved white sound-wave lines (like a WiFi symbol). | Spotify.exe | electron | Bottom bar: playback controls (play/pause, skip, progress bar). Left sidebar: Home, Search, Library. Now Playing in bottom-left. |
| Microsoft Word | Blue square with large white letter 'W'. | WINWORD.EXE | native_win32 + COM | Use win32com.client for programmatic document operations (faster and more reliable than GUI). Ribbon at top. Quick Access Toolbar top-left. |
| Microsoft Excel | Green square with large white letter 'X' (looks like a spreadsheet grid). | EXCEL.EXE | native_win32 + COM | COM automation preferred: `import win32com.client; xl = win32com.client.Dispatch('Excel.Application')`. Ribbon navigation for one-off GUI actions. |
| Microsoft PowerPoint | Orange/coral square with large white letter 'P'. | POWERPNT.EXE | native_win32 + COM | COM automation preferred. Slide panel on left, main editing canvas center, notes bottom. |
| Microsoft Outlook | Blue square with white envelope/O combination. | OUTLOOK.EXE | native_win32 + COM | COM automation: `win32com.client.Dispatch('Outlook.Application')`. Navigation pane left, reading pane right. |
| Adobe Photoshop | Blue square with white 'Ps' text. | Photoshop.exe | native_win32 | Tools in left toolbar. Options bar below menu. Layers panel right. Properties right. OCR works on panels/menus. |
| Adobe Illustrator | Yellow/orange square with white 'Ai' text. | Illustrator.exe | native_win32 | Tools left. Artboard center. Control bar top. Panels right. |
| Adobe Premiere Pro | Purple square with white 'Pr' text. | Premiere Pro.exe | native_win32 | Timeline at bottom. Project panel bottom-left. Program monitor top-right. |
| Adobe After Effects | Dark blue/purple square with 'Ae' text. | AfterFX.exe | native_win32 | Composition viewer center. Timeline bottom. Effects panel right. |
| Adobe XD | Pink/rose square with 'Xd' text. | Adobe XD.exe | native_win32 | Design panel left. Canvas center. Properties right. |
| Windows File Explorer | Yellow folder icon with white/cream pages inside. | explorer.exe | native_win32 | Navigation pane left (Quick Access, drives, OneDrive). Address bar at top (click once or press Alt+D to edit). Search bar top-right. |
| Windows Terminal | Dark terminal window icon with colored text/lines. Usually "Windows Terminal" or "PowerShell" in title bar. | WindowsTerminal.exe | native_win32 | Tab bar at top. Input at bottom of current pane. Right-click title bar for settings. Ctrl+Shift+T for new tab. |
| Windows Settings | Gear icon, simple cog. Title bar shows "Settings". | SystemSettings.exe | native_win32 | Category list on left. Settings in main area. Search bar at top. |
| Task Manager | Colored bar chart icon. "Task Manager" title. | Taskmgr.exe | native_win32 | Tabs at top: Processes, Performance, App history, Startup, Users, Details, Services. Right-click process for options. |
| Notepad | Blank white/cream paper with faint ruled lines. "Notepad" in title bar. | notepad.exe | native_win32 | Simple text area. Menu bar: File, Edit, Format, View, Help. OCR fully works. |
| Notepad++ | Green chameleon (lizard/gecko) icon. | notepad++.exe | native_win32 | Document tabs at top. Code editing area. Plugin menu. Find: Ctrl+F. |
| Paint (MS Paint) | Palette and brush icon, colorful. | mspaint.exe | native_win32 | Canvas center. Tools on left ribbon or top. Colors at bottom or top. |
| Calculator | Simple calculator icon. "Calculator" in title bar. | CalculatorApp.exe | native_win32 | Number pad center. Mode selector (Standard/Scientific) top. |
| Snipping Tool / Snip & Sketch | Scissors icon. | SnippingTool.exe | native_win32 | New snip button top. Mode selector. OCR works. |
| VLC Media Player | Orange traffic cone with white stripes. | vlc.exe | native_win32 | Playback controls at bottom. Menu bar at top. Playlist accessible via View menu. |
| Winamp | Green/gray equalizer/wave shape (legacy). | winamp.exe | native_win32 | Compact player skin. Controls at bottom. Playlist panel separate. |
| WinRAR | Stack of compressed files or archive icon. Yellow/gold color. | WinRAR.exe | native_win32 | File list in main area. Toolbar at top. OCR works. |
| 7-Zip | Blue/gray archive icon with 7Z text. | 7zFM.exe | native_win32 | File browser in main area. OCR works. |
| Postman | Orange/yellow rocket or abstract star shape with "Postman" text. | Postman.exe | electron | Collections in left sidebar. Request builder in main area. Send button prominent. |
| Insomnia | Purple/magenta abstract shape. | Insomnia.exe | electron | Collection sidebar. Request area. |
| Docker Desktop | Blue whale carrying colorful shipping containers on its back. | Docker Desktop.exe | electron | Container list in main area. Images, Volumes tabs. Dashboard metrics. |
| GitHub Desktop | Dark cat silhouette (Octocat) or simple circular logo. | GitHubDesktop.exe | electron | Repository list left. Branch/commit info top. Changes in main area. |
| Git Kraken | Blue trident/fork-like shape (kraken tentacles). | gitkraken.exe | electron | Visual commit graph in center. Left panel for repos. |
| Android Studio | Green stylized Android robot head (antenna + round head). | studio64.exe | java_swing | Project tree left. Code editor center. Run button top. Logcat bottom. Command: Shift+Shift for search. |
| IntelliJ IDEA | Black/dark square with colorful geometric squares or 'IJ' monogram. | idea64.exe | java_swing | Project panel left. Editor center. Terminal bottom. Ctrl+Shift+A for all actions. |
| PyCharm | Black square with yellow/green abstract shapes. | pycharm64.exe | java_swing | Same as IntelliJ. Python-specific run configs. |
| Eclipse | Purple circle with horizontal white line (crescent-like). | eclipse.exe | java_swt | Package Explorer left. Editor center. Console bottom. |
| OBS Studio | Dark gray/black circle with recording button. "OBS Studio" in title. | obs64.exe | native_win32 | Scene list bottom-left. Source list bottom-right. Preview monitor center. Start Streaming/Recording bottom-right. |
| Blender | Orange flower-like pinwheel or abstract O shape. | blender.exe | opengl | **ENTIRE UI is OpenGL — screen_ocr FAILS everywhere. visual_click + visual_inspect required for ALL elements.** Layout: Properties right, Timeline bottom, Viewport center, Outliner top-right. |
| Unity | Black/white Unity logo — abstract white square with smaller squares, or stylized 'U'. | Unity.exe | native_win32 | Game view and Scene view tabs (center). Hierarchy (left). Project (bottom). Inspector (right). Play button top-center. |
| Unreal Engine | Blue circle with white angular UE monogram. | UnrealEditor.exe | native_win32 | Viewport center. World Outliner top-right. Details bottom-right. Content Browser bottom. |
| Steam | Dark blue/navy game controller or circle with radiating lines. | steam.exe | html_embedded | Library list left (html). Store pages are browser-rendered. My Games in main area. |
| Epic Games Launcher | Black background with abstract geometric 'E' shape. | EpicGamesLauncher.exe | html_embedded | Library, Store, Friends tabs in left navigation. |
| Spotify | Green circle with three white curved signal/wave lines. | Spotify.exe | electron | (same as above — listed again for emphasis) Bottom bar has all playback controls. |
| WhatsApp Desktop | Green square with white phone handset inside a speech bubble. | WhatsApp.exe | electron | Chat list left. Message input bottom. Search: Ctrl+F. |
| Telegram Desktop | Blue circle with white abstract bird/plane shape. | Telegram.exe | electron | Chat list left. Message input bottom. Media tabs in chat. |
| Signal Desktop | Blue circle with white speech bubble. | Signal.exe | electron | Contact/chat list left. Message input bottom. |
| Skype | Blue circle with white 'S' (stylized). | Skype.exe | electron | Chat list left. Video/call controls. |
| Microsoft Paint 3D | Colorful 3D cube or rainbow mountain icon. | PaintSplit.exe | native_win32 | 3D view canvas. Toolbar right. |
| Cortana | Blue/purple circle with microphone. | SearchApp.exe | html_embedded | Search input at top. Results below. |
| Snipping Tool | Scissors icon. | SnippingTool.exe | native_win32 | New button to start capture. Mode dropdown. |
| Snagit | Yellow/orange rectangle with S. | Snagit.exe | native_win32 | Capture button. Library of past captures. |
| Greenshot | Green camera/shutter icon. | Greenshot.exe | native_win32 | System tray app. Print Screen triggers capture. |
| ShareX | Orange/red S or circle shape. | ShareX.exe | native_win32 | Main window shows capture modes. |
| Loom | Purple/dark circle with play button. | Loom.exe | electron | Record button. Library of recordings. |
| Figma (web, in Chrome) | When accessing figma.com in Chrome — Figma logo in tab. | chrome.exe | html | Note: web version uses HTML, not WebGL like desktop. browser_extract_text works. |
| Canva | Blue square with colorful diamond/flower C logo. | Browser (canva.com) | html | Web-only. Use browser tools. Design canvas in center. |
| Miro | Yellow/golden circle with white M. | Browser (miro.com) | html | Online whiteboard. browser_navigate + browser_extract_text work. Canvas for visual_inspect. |
| Jira | Blue square with stylized J arrow shape. | Browser (atlassian.net) | html | Web-only. Issue list, board view, backlog. |
| Confluence | Blue square with C outline. | Browser (atlassian.net) | html | Web-only. Pages in left tree. Content in main area. |
| Trello | Blue square with white horizontal lines (T shape). | Browser (trello.com) | html | Web-only. Boards with card lists. |
| Linear | Purple/magenta square with abstract L. | linear.app (browser) | html | Issue tracker. Cycles, Projects in left nav. |
| GitHub (web) | Dark circle with white Octocat (cat with tentacles). | Browser (github.com) | html | Repo list, code view, PR list. |
| Vercel Dashboard | Black/dark background with white triangle logo. | Browser (vercel.com) | html | Project list, deployment logs. |
| Netlify | Teal/cyan background with white abstract diamond. | Browser (netlify.com) | html | Site list, deploy log. |
| Supabase | Green circle with S. | Browser (supabase.com) | html | Table Editor, SQL Editor, Auth, Storage in left nav. |
| Firebase Console | Orange/yellow background with flame icon. | Browser (firebase.google.com) | html | Left nav: Firestore, Auth, Storage, Functions. |
| AWS Console | Orange/yellow background with "aws" text. | Browser (console.aws.amazon.com) | html | Services grid. Top search bar for quick navigation. |
| Google Cloud Console | Blue/white Google Cloud logo. | Browser (console.cloud.google.com) | html | Navigation menu top-left. Services in main. |
| Azure Portal | Blue square with white infinity/Azure logo. | Browser (portal.azure.com) | html | Left sidebar nav. Dashboard in center. |
| Figma Community | Figma logo in tab + "Community" in URL/tab title. | Figma.exe or browser | electron_webgl | Community page canvas is WebGL. Same rules as Figma desktop. |
| Claude (Anthropic) | Orange/amber background with abstract A or Claude logo. | Browser (claude.ai) | html | Chat input at bottom. Conversation in center. |
| ChatGPT | Dark background with white OpenAI logo (abstract circle O). | Browser (chat.openai.com) | html | Chat input at bottom. Conversation center. |
| Gemini | Blue/multicolor Google Gemini logo. | Browser (gemini.google.com) | html | Chat input. |
| Perplexity AI | Black background with purple P logo. | Browser (perplexity.ai) | html | Search input prominent. Answer in main area. |
