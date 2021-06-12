#!/usr/bin/env python

import wx
import wx.lib.mixins.inspection

import sys
import os.path
import esptool
import threading
import images as images
from serial import SerialException
from serial.tools import list_ports

__auto_select__ = "Auto-select"
__auto_select_explanation__ = "(first port with Espressif device)"

# ---------------------------------------------------------------------------


# See discussion at http://stackoverflow.com/q/41101897/131929
class RedirectText:
    def __init__(self, text_ctrl):
        self.__out = text_ctrl

    def write(self, string):
        if string.startswith("\r"):
            # carriage return -> remove last line i.e. reset position to start of last line
            current_value = self.__out.GetValue()
            last_newline = current_value.rfind("\n")
            new_value = current_value[:last_newline + 1]  # preserve \n
            new_value += string[1:]  # chop off leading \r
            wx.CallAfter(self.__out.SetValue, new_value)
        else:
            wx.CallAfter(self.__out.AppendText, string)

    # noinspection PyMethodMayBeStatic
    def flush(self):
        # noinspection PyStatementEffect
        None

    # esptool >=3 handles output differently of the output stream is not a TTY
    # noinspection PyMethodMayBeStatic
    def isatty(self):
        return True

# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
class FlashingThread(threading.Thread):
    def __init__(self, parent, config):
        threading.Thread.__init__(self)
        self.daemon = True
        self._parent = parent
        self._config = config

    def run(self):
        try:
            command = []

            if not self._config.port.startswith(__auto_select__):
                command.append("--port")
                command.append(self._config.port.split(" - ")[0])

            command.extend(["--chip", "esp32",
                            "--baud", "921600",
                            "--before", "default_reset",
                            "--after", "hard_reset",
                            "write_flash",
                                # https://github.com/espressif/esptool/issues/599
                                "--flash_freq", "80m",
                                "--flash_mode", "dio",
                                "--flash_size", "detect",
                                "0x10000", self._config.firmware_path])

            print("Command: esptool.py %s\n" % " ".join(command))

            self._parent.button.SetLabel("Flashing...")
            self._parent.button.SetForegroundColour(wx.NullColour)
            self._parent.button.Disable()

            esptool.main(command)

            self._parent.button.SetLabel("Flash again")
            self._parent.button.Enable()

            msg = "Firmware successfully flashed."
            dlg = wx.MessageDialog(None, msg)
            dlg.ShowModal()
        except Exception as e:
            self._parent.report_error(str(e), caption="Flash failed.", fromFlash=True)


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DTO between GUI and flashing thread
class FlashConfig:
    def __init__(self):
        self.firmware_path = None
        self.port = __auto_select__ + " " + __auto_select_explanation__

# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
class MyFileDropTarget(wx.FileDropTarget):
    def __init__(self, onDrop):
        wx.FileDropTarget.__init__(self)
        self._onDrop = onDrop

    def OnDropFiles(self, x, y, filenames):
        return self._onDrop(filenames)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
class NodeMcuFlasher(wx.Frame):

    def __init__(self, parent, title):
        wx.Frame.__init__(self, parent, -1, title, size=(450, 190),
                          style=wx.DEFAULT_FRAME_STYLE | wx.NO_FULL_REPAINT_ON_RESIZE)
        self.SetMinSize(size=(450, 190))
        self._config = FlashConfig()

        self._set_icons()
        self._init_ui()

        sys.stdout = RedirectText(self.console_ctrl)

        file_drop_target = MyFileDropTarget(self.set_filepath)
        self.SetDropTarget(file_drop_target)

        if len(sys.argv) > 1:
            filenames = sys.argv[1:]
            self.set_filepath(filenames)

        self.Centre(wx.BOTH)
        self.Show(True)
        # print("Connect your device")
        # print("\nIf you chose the serial port auto-select feature")
        # print("you might need to turn off Bluetooth")

    def _init_ui(self):
        def on_reload(event):
            self.choice.SetItems(self._get_serial_ports())

        def on_clicked(event):
            if self._config.firmware_path != None:
                self.console_ctrl.SetValue("")
                worker = FlashingThread(self, self._config)
                worker.start()

        def on_select_port(event):
            choice = event.GetEventObject()
            self._config.port = choice.GetString(choice.GetSelection())

        def on_pick_file(event):
            filepath = event.GetPath().replace("'", "")
            self.set_filepath([filepath])

        panel = wx.Panel(self)

        hbox = wx.BoxSizer(wx.HORIZONTAL)

        fgs = wx.FlexGridSizer(4, 2, 10, 10)

        self.choice = wx.Choice(panel, choices=self._get_serial_ports())
        self.choice.Bind(wx.EVT_CHOICE, on_select_port)
        self._select_configured_port()

        reload_button = wx.Button(panel, label="Reload")
        reload_button.Bind(wx.EVT_BUTTON, on_reload)
        reload_button.SetToolTip("Reload serial device list")

        self.filepath_text = wx.TextCtrl(panel, style=wx.TE_READONLY)

        self.file_picker = wx.FilePickerCtrl(panel, style=wx.FLP_OPEN|wx.FLP_FILE_MUST_EXIST, wildcard="*.bin")
        self.file_picker.Bind(wx.EVT_FILEPICKER_CHANGED, on_pick_file)
        self.file_picker.SetFocus()

        serial_boxsizer = wx.BoxSizer(wx.HORIZONTAL)
        serial_boxsizer.Add(self.choice, 1, wx.EXPAND)
        serial_boxsizer.Add(reload_button, flag=wx.LEFT, border=5)

        file_boxsizer = wx.BoxSizer(wx.HORIZONTAL)
        file_boxsizer.Add(self.filepath_text, 1, wx.EXPAND)
        file_boxsizer.Add(self.file_picker, flag=wx.LEFT, border=5)

        font = wx.Font(15, wx.FONTFAMILY_DEFAULT,  wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.button = wx.Button(panel, -1, "Drop your firmware", size=wx.Size(-1, 100))
        self.button.Bind(wx.EVT_BUTTON, on_clicked)
        self.button.SetFont(font)
        self.button.SetForegroundColour(wx.Colour("RED"))
        # self.button.Disable()

        self.console_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        self.console_ctrl.SetFont(wx.Font((0, 13), wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                                          wx.FONTWEIGHT_NORMAL))
        self.console_ctrl.SetBackgroundColour(wx.WHITE)
        self.console_ctrl.SetForegroundColour(wx.BLUE)
        self.console_ctrl.SetDefaultStyle(wx.TextAttr(wx.BLUE))

        port_label = wx.StaticText(panel, label="Serial port")
        file_label = wx.StaticText(panel, label="Firmware")
        console_label = wx.StaticText(panel, label="Console")

        fgs.AddMany([file_label, (file_boxsizer, 1, wx.EXPAND),
                    (wx.StaticText(panel, label="")), (self.button, 1, wx.EXPAND),
                    port_label, (serial_boxsizer, 1, wx.EXPAND),
                    (console_label, 1, wx.EXPAND), (self.console_ctrl, 1, wx.EXPAND)])
        fgs.AddGrowableRow(3, 1)
        fgs.AddGrowableCol(1, 1)
        hbox.Add(fgs, proportion=2, flag=wx.ALL | wx.EXPAND, border=15)
        panel.SetSizer(hbox)

    def _select_configured_port(self):
        count = 0
        for item in self.choice.GetItems():
            if item == self._config.port:
                self.choice.Select(count)
                break
            count += 1

    @staticmethod
    def _get_serial_ports():
        ports = [__auto_select__ + " " + __auto_select_explanation__]
        for port, desc, hwid in sorted(list_ports.comports()):
            ports.append(port + " - " + desc)
        return ports

    def _set_icons(self):
        self.SetIcon(images.Icon.GetIcon())

    def report_error(self, message, caption="Error", fromFlash=False):
        dlg = wx.MessageDialog(None, message, caption=caption, style=wx.ICON_ERROR)
        dlg.ShowModal()
        self.console_ctrl.AppendText("\n" + message.replace("\n\n", "\n") + "\n\n")

        if fromFlash:
            self.button.SetLabel("Try flash again")
            self.button.SetForegroundColour(wx.Colour("FOREST GREEN"))
            self.button.Enable()

    def set_filepath(self, filenames):
        msg = "Some thing error."
        for filepath in filenames:
            magic = 0x00
            try:
                firmware = open(filepath, 'rb')
                magic = int.from_bytes(firmware.read(1), "big")
                firmware.close()
            except IOError as err:
                msg = "Error opening binary '{}'\n\n{}".format(filepath, err)
                break

            if magic != esptool.ESPLoader.ESP_IMAGE_MAGIC:
                msg = "The firmware binary is invalid\n\n"
                msg += "magic byte={:02X}, should be {:02X}".format(magic, esptool.ESPLoader.ESP_IMAGE_MAGIC)
                break

            self._config.firmware_path = filepath
            self.file_picker.SetPath(filepath)
            self.filepath_text.SetValue(filepath)
            self.button.SetLabel("Flash ESP32")
            self.button.SetForegroundColour(wx.Colour("FOREST GREEN"))
            # self.button.Enable()
            self.button.SetFocus()
            return True

        r = threading.Timer(0, self.report_error, [msg])
        r.start()
        return False

# ---------------------------------------------------------------------------

# ----------------------------------------------------------------------------
class App(wx.App, wx.lib.mixins.inspection.InspectionMixin):
    def OnInit(self):
        wx.SystemOptions.SetOption("mac.window-plain-transition", 1)
        self.SetAppName("ESP32 PyFlasher")

        frame = NodeMcuFlasher(None, "ESP32 PyFlasher")
        frame.Show()

        return True


# ---------------------------------------------------------------------------
def main():
    app = App(False)
    app.MainLoop()
# ---------------------------------------------------------------------------


if __name__ == '__main__':
    __name__ = 'Main'
    main()

