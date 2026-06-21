const { app, BrowserWindow, Menu } = require('electron');
const path = require('path');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 440,
    height: 780,
    minWidth: 380,
    minHeight: 600,
    title: "Jarvis",
    backgroundColor: "#060A14",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      // webSecurity stays ON (the secure default). The phone UI loads from file:// and reaches
      // the Hermes server over WebSocket (not subject to same-origin) and via fetch with the
      // server's CORS allow-list — so disabling same-origin protection is unnecessary and a
      // serious footgun for a desktop wrapper. Escape hatch for local debugging only:
      // set JARVIS_DESKTOP_INSECURE=1 before launch.
      webSecurity: process.env.JARVIS_DESKTOP_INSECURE !== '1',
    }
  });

  // Load the copied phone frontend resources
  mainWindow.loadFile(path.join(__dirname, 'phone', 'index.html'));

  // Disable standard toolbar menus for a clean native app look
  Menu.setApplicationMenu(null);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.on('ready', () => {
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});
