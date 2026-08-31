import addonHandler
import gui
import os.path
import sys
import wx

addon = addonHandler.getCodeAddon()
addonName = addon.name
addonDir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "globalPlugins", addonName)
)
sys.path.append(addonDir)
from donate_dialog import requestDonations  # noqa: E402

sys.path.remove(sys.path[-1])

addonHandler.initTranslation()


def onInstall():
    gui.mainFrame.prePopup()
    wx.CallAfter(requestDonations, gui.mainFrame)
    gui.mainFrame.postPopup()
