#!/usr/bin/env python

import wx
import wx.lib.mixins.inspection

import sys
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
                command.append(self._config.port)

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

            esptool.main(command)

            # The last line printed by esptool is "Staying in bootloader." -> some indication that the process is
            # done is needed
            print("\nFirmware successfully flashed. Unplug/replug or reset device \nto switch back to normal boot "
                  "mode.")
        except SerialException as e:
            self._parent.report_error(str(e))
            raise e
        except esptool.FatalError as e:
            self._parent.report_error(str(e))
            raise e


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DTO between GUI and flashing thread
class FlashConfig:
    def __init__(self):
        self.firmware_path = None
        self.port = __auto_select__ + " " + __auto_select_explanation__

# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
class NodeMcuFlasher(wx.Frame):

    def __init__(self, parent, title):
        wx.Frame.__init__(self, parent, -1, title, size=(700, 300),
                          style=wx.DEFAULT_FRAME_STYLE | wx.NO_FULL_REPAINT_ON_RESIZE)
        self._config = FlashConfig()

        self._set_icons()
        self._init_ui()

        sys.stdout = RedirectText(self.console_ctrl)

        self.Centre(wx.BOTH)
        self.Show(True)
        print("Connect your device")
        print("\nIf you chose the serial port auto-select feature you might need to ")
        print("turn off Bluetooth")

    def _init_ui(self):
        def on_reload(event):
            self.choice.SetItems(self._get_serial_ports())

        def on_clicked(event):
            self.console_ctrl.SetValue("")
            self.console_ctrl.SetForegroundColour(wx.BLUE)
            worker = FlashingThread(self, self._config)
            worker.start()

        def on_select_port(event):
            choice = event.GetEventObject()
            self._config.port = choice.GetString(choice.GetSelection())

        def on_pick_file(event):
            self._config.firmware_path = event.GetPath().replace("'", "")

        panel = wx.Panel(self)

        hbox = wx.BoxSizer(wx.HORIZONTAL)

        fgs = wx.FlexGridSizer(4, 2, 10, 10)

        self.choice = wx.Choice(panel, choices=self._get_serial_ports())
        self.choice.Bind(wx.EVT_CHOICE, on_select_port)
        self._select_configured_port()

        reload_button = wx.Button(panel, label="Reload")
        reload_button.Bind(wx.EVT_BUTTON, on_reload)
        reload_button.SetToolTip("Reload serial device list")

        file_picker = wx.FilePickerCtrl(panel, style=wx.FLP_USE_TEXTCTRL)
        file_picker.Bind(wx.EVT_FILEPICKER_CHANGED, on_pick_file)

        serial_boxsizer = wx.BoxSizer(wx.HORIZONTAL)
        serial_boxsizer.Add(self.choice, 1, wx.EXPAND)
        serial_boxsizer.Add(reload_button, flag=wx.LEFT, border=10)

        button = wx.Button(panel, -1, "Flash ESP32")
        button.Bind(wx.EVT_BUTTON, on_clicked)

        self.console_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        self.console_ctrl.SetFont(wx.Font((0, 13), wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                                          wx.FONTWEIGHT_NORMAL))
        self.console_ctrl.SetBackgroundColour(wx.WHITE)
        self.console_ctrl.SetForegroundColour(wx.BLUE)
        self.console_ctrl.SetDefaultStyle(wx.TextAttr(wx.BLUE))

        port_label = wx.StaticText(panel, label="Serial port")
        file_label = wx.StaticText(panel, label="ESP32 firmware")
        console_label = wx.StaticText(panel, label="Console")

        fgs.AddMany([
                    port_label, (serial_boxsizer, 1, wx.EXPAND),
                    file_label, (file_picker, 1, wx.EXPAND),
                    (wx.StaticText(panel, label="")), (button, 1, wx.EXPAND),
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
            ports.append(port)
        return ports

    def _set_icons(self):
        self.SetIcon(images.Icon.GetIcon())

    def report_error(self, message):
        self.console_ctrl.SetForegroundColour(wx.RED)
        self.console_ctrl.SetValue(message)

    def log_message(self, message):
        self.console_ctrl.AppendText(message)

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

