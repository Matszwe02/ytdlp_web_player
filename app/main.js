"use strict";

const { app, BrowserWindow, net } = require("electron");
const path = require("path");
const fs = require("fs");

let mainWindow = null;
let backendProcess = null;


const getPythonScriptPath = () =>
{
    const cliFile = fs.readdirSync(__dirname).find(file => file.includes('CLI'));
    return path.join(__dirname, cliFile);
};


const startBackend = () =>
{
    let script = getPythonScriptPath();
    const args = [`--LINKED_PID=${process.pid}`];

    backendProcess = require("child_process").spawn(script, args);
    backendProcess.stdout.pipe(process.stdout);
    backendProcess.stderr.pipe(process.stderr);
};


const checkBackend = (url, callback) =>
{
    const request = net.request(url);
    request.on("response", (response) => { callback(response.statusCode === 200); });
    request.on("error", () => { callback(false); });
    request.end();
};


app.on("ready", function ()
{
    mainWindow = new BrowserWindow({
        width: 800,
        height: 600,
        icon: path.join(__dirname, "favicon48.png"),
        darkTheme: true,
        resizeable: true,
    });
    mainWindow.setMenuBarVisibility(false)
    mainWindow.loadFile('splashscreen.html');
    startBackend();

    const tryToLoad = () =>
    {
        const url = `http://localhost:5000/`;
        checkBackend(url, (success) =>
        {
            if (success)
                mainWindow.loadURL(url);
            else
                setTimeout(tryToLoad, 1000);
        });
    };
    tryToLoad();
});
