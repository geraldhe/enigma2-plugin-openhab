# -*- coding: UTF-8 -*-

from . import _, config_root, debug
from setup import SetupWindow
from client import RestClient

from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.config import ConfigText, ConfigNothing, ConfigSlider, ConfigOnOff, ConfigSelection, getConfigListEntry
from Components.config import KEY_LEFT, KEY_RIGHT, KEY_OK
from Components.ConfigList import ConfigListScreen
from Components.ActionMap import ActionMap
from enigma import eTimer
from re import compile as re_compile

LABEL_PATTERN = re_compile(r"([^[]+)\s+\[([^]]+)\]")


class SitemapWidget(object):

    def __init__(self, item, sub_page):
        self.item = item
        self.sub_page = sub_page
    
    def send_command(self, cmd=None):
        if self.item:
            item_type = self.item["type"]
            item_name = self.item["name"].encode("UTF-8")
            if cmd:
                cmd = str(cmd)
            elif item_type in ["SwitchItem", "DimmerItem", "NumberItem"]:
                cmd = str(self.value)
            if cmd:
                debug("Sending command: type=%s, name=%s, cmd=%s" % (item_type, item_name, cmd))
                client.send_cmd(item_name, cmd)


class StaticWidget(SitemapWidget, ConfigSelection):
    
    def __init__(self, item, sub_page, value):
        SitemapWidget.__init__(self, item, sub_page)
        ConfigSelection.__init__(self, choices=[value])


class SwitchWidget(SitemapWidget, ConfigSelection):
    
    def __init__(self, item, sub_page, mapping=None):
        SitemapWidget.__init__(self, item, sub_page)
        
        if mapping:
            if not isinstance(mapping, list):
                mapping = [mapping]
            choices = map(lambda mi: (mi["command"], mi["label"]), mapping)
            if len(mapping) == 1:
                # button mode
                if mapping[0]["command"] == item["state"]:
                    # disabled: empty text
                    choices = [(item["state"], "")] 
                else:
                    # add ability to send mapped command
                    choices.append((item["state"], mapping[0]["label"]))
        else:
            choices = [("ON", _("on")), ("OFF", _("off"))]
            
        ConfigSelection.__init__(self, choices=choices, default=item["state"])

    def handleKey(self, key):
        if key == KEY_OK:
            debug("[SwitchWidget] KEY_OK pressed")
            self.selectNext()
            self.send_command()
        else:
            ConfigSelection.handleKey(self, key)


class SelectionWidget(SitemapWidget, ConfigSelection):
    
    def __init__(self, item, sub_page, choices):
        SitemapWidget.__init__(self, item, sub_page)
        ConfigSelection.__init__(self, default=item.get("state") if item else None, choices=choices)


class SliderWidget(SitemapWidget, ConfigSlider):
    
    MIN_VAL = 0
    MAX_VAL = 100
    
    def __init__(self, item, sub_page, increment=5):
        SitemapWidget.__init__(self, item, sub_page)
        ConfigSlider.__init__(self, default=int(item["state"]), increment=increment, limits=(SliderWidget.MIN_VAL, SliderWidget.MAX_VAL))

    def handleKey(self, key):
        if key == KEY_OK:
            debug("[SliderWidget] KEY_OK pressed")
            if self.value == SliderWidget.MIN_VAL:
                self.value = SliderWidget.MAX_VAL
            else:
                self.value = SliderWidget.MIN_VAL
            self.send_command()
        else:
            ConfigSlider.handleKey(self, key)

    def getMulti(self, selected):
            self.checkValues()
            return ("text", self.getText())

    def getText(self):
            return "%d %%" % self.value


class ShutterWidget(SitemapWidget, ConfigSelection):
    
    def __init__(self, item, sub_page, value):
        SitemapWidget.__init__(self, item, sub_page)
        ConfigSelection.__init__(self, choices=[(value, "%s %%" % value)])

    def handleKey(self, key):
        debug("[ShutterWidget] key pressed: " + str(key))
        if key == KEY_OK:
            self.send_command("STOP")
        elif key == KEY_LEFT:
            self.send_command("UP")
        elif key == KEY_RIGHT:
            self.send_command("DOWN")
        else:
            ConfigSelection.handleKey(self, key)


class FrameWidget(SitemapWidget, ConfigNothing):
    
    def __init__(self, item, sub_page):
        SitemapWidget.__init__(self, item, sub_page)
        ConfigNothing.__init__(self)


class SitemapWindow(Screen, ConfigListScreen):

    skin = """
        <screen position="center,center" size="570,420" title="">
            <widget name="config" position="0,0" size="570,420" scrollbarMode="showOnDemand" />
        </screen>"""

    def __init__(self, session, sitemap):
        Screen.__init__(self, session)
        ConfigListScreen.__init__(self, [], on_change=self.item_changed)

        self.setTitle("Loading sitemap...")
        
        self["actions"] = ActionMap(["SetupActions", "OkCancelActions", "ColorActions"],
        {
#            "green": self.go_into,
            "yellow": self.show_settings,
            "red": self.go_up,
            "cancel": self.go_up
        }, -2)
        self.sitemap = sitemap
        self.refreshing = False
        self.refresh_data()
        
        self.refreshTimer = eTimer()
        self.refreshTimer.callback.append(self.refresh_data)
        self.refreshTimer.start(config_root.refresh.value*1000)
    
    def refresh_data(self, reset_index=False):
    
        def download_done(sitemap):
            self.refreshing = False
            debug("Sitemap loaded successfully: %s" % self.sitemap)
            if "homepage" in sitemap:
                sitemap = sitemap["homepage"]
            self.setTitle(sitemap["title"].encode("UTF-8"))
            self.parent_page = sitemap.get("parent", {}).get("id")
            if self.parent_page:
                self.parent_page = self.parent_page.encode("UTF-8")
            self["config"].list = self.load_widgets([], sitemap)
            if reset_index:
                self["config"].setCurrentIndex(0)
        
        def download_err(error):
            self.refreshing = False
            debug("Error while loading sitemap %s: %s" % (self.sitemap, str(error)))
            self.session.openWithCallback(lambda result: self.show_settings() if result else self.close(), MessageBox, 
                                          _("Error loading sitemap: %s\nOpen settings window to configure connection parameters?") % self.sitemap, MessageBox.TYPE_YESNO)
    
        if self.refreshing:
            return
        self.refreshing = True
        debug("Loading sitemap: %s" % self.sitemap)
        client.get_sitemap(self.sitemap).addCallbacks(callback=download_done, errback=download_err)

    def load_widgets(self, items, sitemap):
        widget_list = sitemap.get("widget") or []
        if not isinstance(widget_list, list):
            widget_list = [widget_list]

        for widget_data in widget_list:
            debug("Processing widget: " + unicode(widget_data).encode("UTF-8"))
            widget_type = widget_data["type"]
            widget_label = widget_data["label"].encode("UTF-8")
            match = LABEL_PATTERN.match(widget_label)
            if match is None:
                widget_label1 = widget_label
                widget_label2 = ""
            else:
                widget_label1 = match.group(1)
                widget_label2 = match.group(2)
            widget_item = widget_data.get("item")
            item_state = widget_item["state"] if widget_item else None
            if item_state is None or item_state == "Undefined":
                item_state = ""
            sub_page = widget_data.get("linkedPage", {}).get("id")
            if sub_page:
                sub_page = sub_page.encode("UTF-8")

            if widget_type == "Text" or widget_type == "Group":
                items.append(getConfigListEntry(widget_label1, StaticWidget(widget_item, sub_page, widget_label2 or item_state)))

            elif widget_type == "Switch":
                if widget_item and widget_item.get("type") == "RollershutterItem":
                    items.append(getConfigListEntry(widget_label1, ShutterWidget(widget_item, sub_page, item_state)))
                else:
                    items.append(getConfigListEntry(" ".join([widget_label1, widget_label2]), 
                                                    SwitchWidget(widget_item, sub_page, mapping=widget_data.get("mapping"))))

            elif widget_type == "Slider":
                items.append(getConfigListEntry(widget_label1, SliderWidget(widget_item, sub_page)))

            elif widget_type == "Selection":
                choices = map(lambda item: (item["command"], item["label"]), widget_data["mapping"])
                items.append(getConfigListEntry(widget_label1, SelectionWidget(widget_item, sub_page, choices=choices)))

            elif widget_type == "Frame":
                items.append(getConfigListEntry("--- %s ---" % widget_label1, FrameWidget(widget_item, sub_page)))  
                self.load_widgets(items, widget_data)

            else:
                debug("Skipping unknown widget: " + widget_type)
            
            debug("Widget processed: " + widget_type)
        
        return items

    def item_changed(self):
            debug("Item changed: " + str(self["config"].getCurrent()))
            current = self["config"].getCurrent()
            if current:
                current[1].send_command()

    def keyOK(self):
        current = self["config"].getCurrent()
        if current and current[1].sub_page:
            self.go_into(current[1].sub_page)
        else:
            ConfigListScreen.keyOK(self)

    def go_into(self, sub_page):
        sitemap = self.sitemap.split("/", 2)[0]
        self.sitemap = sitemap + "/" + sub_page
        debug("Going into:" + self.sitemap)
        self.refresh_data(reset_index=True)

    def go_up(self):
        if self.sitemap != config_root.sitemap.value and self.parent_page:
            sitemap = self.sitemap.split("/", 2)[0]
            self.sitemap = sitemap + "/" + self.parent_page
            debug("Going up:" + self.sitemap)
            self.refresh_data(reset_index=True)
        else:
            self.close()
    
    def show_settings(self):

        def on_close(settings_saved):
            # if setup has been canceled, do not reload
            if settings_saved:
                create_client()
                self.sitemap = config_root.sitemap.value
                self.refresh_data(reset_index=True)
    
        self.session.openWithCallback(on_close, SetupWindow)

    def close(self):
        self.refreshTimer.stop()
        Screen.close(self)


###########################################################################

client = None

def create_client():
    global client
    params = (config_root.host.value, config_root.port.value, config_root.user.value, config_root.password.value)
    debug("Creating openHAB client: host=%s, port=%d, user=%s, password=%s" % params)
    client = RestClient(*params)

def show_main_window(session):
    create_client()
    session.open(SitemapWindow, config_root.sitemap.value)

def show_settings(session):

    def on_close(settings_saved):
        # if setup has been canceled, do not reload
        if settings_saved:
            show_main_window(session)

    session.openWithCallback(on_close, SetupWindow)

def plugin_main(session, **kwargs):
    if config_root.host.value:
        show_main_window(session)
    else:
        show_settings(session)

###########################################################################

def Plugins(**kwargs):
    return PluginDescriptor(
            name=_("openHAB client"),
            description=_("Simple openHAB client for Enigma2"),
            where = [PluginDescriptor.WHERE_PLUGINMENU, PluginDescriptor.WHERE_EXTENSIONSMENU],
            icon="plugin.png",
            fnc=plugin_main)
