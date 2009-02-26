# Copyright (C) 2007, Eduardo Silva <edsiper@gmail.com>.
# Copyright (C) 2008, One Laptop Per Child
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os

from gettext import gettext as _

# Initialize logging.
import logging
log = logging.getLogger('Terminal')
log.setLevel(logging.DEBUG)
logging.basicConfig()

import gtk
import dbus

import sugar.graphics.toolbutton
from sugar.activity import activity
from sugar import env
from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.palette import Palette
import ConfigParser
import os.path

import vte
import pango

import simplejson

class TerminalActivity(activity.Activity):

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)
        
        self.data_file = None
        
        self.set_title(_('Terminal Activity'))
        #self.connect('key-press-event', self._key_press_cb)

        toolbox = activity.ActivityToolbox(self)

        editbar = activity.EditToolbar()
        toolbox.add_toolbar(_('Edit'), editbar)
        editbar.show()
        editbar.undo.props.visible = False
        editbar.redo.props.visible = False
        editbar.separator.props.visible = False
        editbar.copy.connect('clicked', self._copy_cb)
        editbar.copy.props.accelerator = '<Ctrl><Shift>C'
        editbar.paste.connect('clicked', self._paste_cb)
        editbar.paste.props.accelerator = '<Ctrl><Shift>V'

        newtabbtn = sugar.graphics.toolbutton.ToolButton('list-add')
        newtabbtn.set_tooltip(_("Open New Tab"))
        newtabbtn.props.accelerator = '<Ctrl><Shift>T'
        newtabbtn.connect('clicked', self._open_tab_cb)

        deltabbtn = sugar.graphics.toolbutton.ToolButton('list-remove')
        deltabbtn.set_tooltip(_("Close Tab"))
        deltabbtn.props.accelerator = '<Ctrl><Shift>X'
        deltabbtn.connect('clicked', self._close_tab_cb)

        tabsep = gtk.SeparatorToolItem()
        tabsep.set_expand(True)
        tabsep.set_draw(False)

        # Add a button that will be used to become root easily.
        rootbtn = ToolButton('activity-become-root')
        rootbtn.set_tooltip(_('Become root'))
        rootbtn.connect('clicked', self._become_root_cb)

        prevtabbtn = sugar.graphics.toolbutton.ToolButton('go-previous')
        prevtabbtn.set_tooltip(_("Previous Tab"))
        prevtabbtn.props.accelerator = '<Ctrl><Shift>Left'
        prevtabbtn.connect('clicked', self._prev_tab_cb)

        nexttabbtn = sugar.graphics.toolbutton.ToolButton('go-next')
        nexttabbtn.set_tooltip(_("Next Tab"))
        nexttabbtn.props.accelerator = '<Ctrl><Shift>Right'
        nexttabbtn.connect('clicked', self._next_tab_cb)

        tabbar = gtk.Toolbar()
        tabbar.insert(newtabbtn, -1)
        tabbar.insert(deltabbtn, -1)
        tabbar.insert(tabsep, -1)
        tabbar.insert(rootbtn, -1)
        tabbar.insert(prevtabbtn, -1)
        tabbar.insert(nexttabbtn, -1)
        tabbar.show_all()

        toolbox.add_toolbar(_('Tab'), tabbar)

        activity_toolbar = toolbox.get_activity_toolbar()
        activity_toolbar.share.props.visible = False
        activity_toolbar.keep.props.visible = False

        fullscreenbtn = sugar.graphics.toolbutton.ToolButton('view-fullscreen')
        fullscreenbtn.set_tooltip(_("Fullscreen"))
        fullscreenbtn.props.accelerator = '<Alt>Enter'
        fullscreenbtn.connect('clicked', self._fullscreen_cb)
        activity_toolbar.insert(fullscreenbtn, 2)
        fullscreenbtn.show()
        
        self.set_toolbox(toolbox)
        toolbox.show()
        
        self.notebook = gtk.Notebook()
        self.notebook.set_property("tab-pos", gtk.POS_BOTTOM)
        self.notebook.set_scrollable(True)
        self.notebook.show()

        self.set_canvas(self.notebook)

        self._create_tab(None)

    def _open_tab_cb(self, btn):
        index = self._create_tab(None) 
        self.notebook.page = index

    def _close_tab_cb(self, btn):
        self._close_tab(self.notebook.props.page)

    def _prev_tab_cb(self, btn):
        if self.notebook.props.page == 0:
            self.notebook.props.page = self.notebook.get_n_pages() - 1
        else:
            self.notebook.props.page = self.notebook.props.page - 1
        vt = self.notebook.get_nth_page(self.notebook.get_current_page()).vt
        vt.grab_focus()

    def _next_tab_cb(self, btn):
        if self.notebook.props.page == self.notebook.get_n_pages() - 1:
            self.notebook.props.page = 0
        else:
            self.notebook.props.page = self.notebook.props.page + 1
        vt = self.notebook.get_nth_page(self.notebook.get_current_page()).vt
        vt.grab_focus()

    def _close_tab(self, index):
        self.notebook.remove_page(index)
        if self.notebook.get_n_pages() == 0:
            self.close()
            
    def _tab_child_exited_cb(self, vt):
        for i in range(self.notebook.get_n_pages()):
            if self.notebook.get_nth_page(i).vt == vt:
                self._close_tab(i)
                return
 
    def _tab_title_changed_cb(self, vt):
        for i in range(self.notebook.get_n_pages()):
            if self.notebook.get_nth_page(i).vt == vt:
                label = self.notebook.get_nth_page(i).label
                label.set_text(vt.get_window_title())
                return
 
    def _drag_data_received_cb(self, widget, context, x, y, selection, target, time):
        widget.feed_child(selection.data)
        context.finish(True, False, time)
        return True

    def _create_tab(self, tab_state):
        vt = vte.Terminal()
        vt.connect("child-exited", self._tab_child_exited_cb)
        vt.connect("window-title-changed", self._tab_title_changed_cb)

        vt.drag_dest_set(gtk.DEST_DEFAULT_MOTION|gtk.DEST_DEFAULT_DROP,
               [('text/plain', 0, 0), ('STRING', 0, 1)],
               gtk.gdk.ACTION_DEFAULT|
               gtk.gdk.ACTION_COPY)
        vt.connect('drag_data_received', self._drag_data_received_cb)
        
        self._configure_vt(vt)

        vt.show()
    
        label = gtk.Label()

        scrollbar = gtk.VScrollbar(vt.get_adjustment())
        scrollbar.show()

        box = gtk.HBox()
        box.pack_start(vt)
        box.pack_start(scrollbar)

        box.vt = vt
        box.label = label
        
        index = self.notebook.append_page(box, label)
        self.notebook.show_all()
        self.notebook.props.show_tabs = self.notebook.get_n_pages() > 1

        # Launch the default shell in the HOME directory.
        os.chdir(os.environ["HOME"])

        if tab_state:
            # Restore the environment.
            os.environ['TERMINAL_ENV'] = tab_state['env']
            
            # Restore the scrollback buffer.
            for l in tab_state['scrollback']:
                vt.feed(l + '\r\n')

        box.pid = vt.fork_command()

        self.notebook.props.page = index
        vt.grab_focus()

        return index

    def _copy_cb(self, button):
        vt = self.notebook.get_nth_page(self.notebook.get_current_page()).vt
        if vt.get_has_selection():
            vt.copy_clipboard()

    def _paste_cb(self, button):
        vt = self.notebook.get_nth_page(self.notebook.get_current_page()).vt
        vt.paste_clipboard()

    def _become_root_cb(self, button):
        vt = self.notebook.get_nth_page(self.notebook.get_current_page()).vt
        vt.feed('\r\n')
        vt.fork_command("/bin/su", ('/bin/su', '-'))

    def _fullscreen_cb(self, btn):
        self.fullscreen()

    def _key_press_cb(self, window, event):
        if gtk.gdk.keyval_name(event.keyval) == 'Escape':
            return True
                
        return False

    def read_file(self, file_path):
        if self.metadata['mime_type'] != 'text/plain':
            return

        fd = open(file_path, 'r')
        text = fd.read()
        data = simplejson.loads(text)
        fd.close()

        data_file = file_path

        while self.notebook.get_n_pages():
            self.notebook.remove_page(0)

        for tab in data['tabs']:
            index = self._create_tab(tab)

        self.notebook.props.page = data['current-tab']

    def write_file(self, file_path):
        if not self.metadata['mime_type']:
            self.metadata['mime_type'] = 'text/plain'

        data = {}
        data['current-tab'] = self.notebook.get_current_page()
        data['tabs'] = []

        print "about to save tabs"
        for i in range(self.notebook.get_n_pages()):
            print "tab %d" % i
            page = self.notebook.get_nth_page(i)

            def selected_cb(terminal, c, row, cb_data):
                return 1
            (scrollback_text, attrs) = page.vt.get_text(selected_cb, 1)

            scrollback_lines = scrollback_text.split('\n')

            environment = open('/proc/%d/environ' % page.pid, 'r').read().replace('\0','\n')

            tab_state = { 'env': environment, 'cwd': '', 'scrollback': scrollback_lines }

            data['tabs'].append(tab_state)

        fd = open(file_path, 'w')
        text = simplejson.dumps(data)
        fd.write(text)
        fd.close()
    
    def _get_conf(self, conf, var, default):
        if conf.has_option('terminal', var):
            if isinstance(default, bool):
                return conf.getboolean('terminal', var)
            elif isinstance(default, int):
                return conf.getint('terminal', var)
            else:
                return conf.get('terminal', var)
        else:
            if isinstance(default, bool):
                conf.setboolean('terminal', var, default)
            elif isinstance(default, int):
                conf.setint('terminal', var, default)
            else:
                conf.set('terminal', var, default)

            return default

    def _configure_vt(self, vt):
        conf = ConfigParser.ConfigParser()
        conf_file = os.path.join(env.get_profile_path(), 'terminalrc')
        
        if os.path.isfile(conf_file):
            f = open(conf_file, 'r')
            conf.readfp(f)
            f.close()
        else:
            conf.add_section('terminal')
        
        font = self._get_conf(conf, 'font', 'Monospace')
        vt.set_font(pango.FontDescription(font))

        fg_color = self._get_conf(conf, 'fg_color', '#000000')
        bg_color = self._get_conf(conf, 'bg_color', '#FFFFFF')
        vt.set_colors(gtk.gdk.color_parse(fg_color), gtk.gdk.color_parse(bg_color), [])
                            
        blink = self._get_conf(conf, 'cursor_blink', False)
        vt.set_cursor_blinks(blink)

        bell = self._get_conf(conf, 'bell', False)
        vt.set_audible_bell(bell)
        
        scrollback_lines = self._get_conf(conf, 'scrollback_lines', 1000)
        vt.set_scrollback_lines(scrollback_lines)

        vt.set_allow_bold(True)
        
        scroll_key = self._get_conf(conf, 'scroll_on_keystroke', True)
        vt.set_scroll_on_keystroke(scroll_key)

        scroll_output = self._get_conf(conf, 'scroll_on_output', False)
        vt.set_scroll_on_output(scroll_output)
        
        emulation = self._get_conf(conf, 'emulation', 'xterm')
        vt.set_emulation(emulation)

        visible_bell = self._get_conf(conf, 'visible_bell', False)
        vt.set_visible_bell(visible_bell)

        conf.write(open(conf_file, 'w'))
