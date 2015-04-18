# -*- coding: utf-8 -*-
# Copyright 2004-2007 Joe Wreschnig, Michael Urman, Iñigo Serna
#           2009-2010 Steven Robertson
#           2012-2013 Nick Boultbee
#           2009-2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk, GLib, Pango

from quodlibet import config
from quodlibet import qltk
from quodlibet import util
from quodlibet.formats import PEOPLE

from quodlibet.util import format_rating, connect_obj
from quodlibet.qltk.ccb import ConfigCheckButton
from quodlibet.qltk.textedit import PatternEditBox
from quodlibet.pattern import XMLFromMarkupPattern


EMPTY = _("Songs not in an album")
PATTERN = """[b]<album|<album>|%s>[/b]<date| (<date>)>
[small]<~discs|<~discs> - ><~tracks> - <~long-length>[/small]
<~people>""" % EMPTY


class FakeAlbum(dict):

    def get(self, key, default="", connector=" - "):
        if key[:1] == "~" and '~' in key[1:]:
            return connector.join(map(self.get, util.tagsplit(key)))
        elif key[:1] == "~" and key[-4:-3] == ":":
            func = key[-3:]
            key = key[:-4]
            return "%s<%s>" % (util.tag(key), func)
        elif key in self:
            return self[key]
        return util.tag(key)

    __call__ = get

    def comma(self, key):
        value = self.get(key)
        if isinstance(value, (int, float)):
            return value
        return value.replace("\n", ", ")

PEOPLE
_SOME_PEOPLE = "\n".join([util.tag("artist"), util.tag("performer"),
                         util.tag("composer"), util.tag("arranger"), ])


class Preferences(qltk.UniqueWindow):

    _EXAMPLE_ALBUM = FakeAlbum({
        "date": "2010-10-31",
        "~length": util.format_time_display(6319),
        "~long-length": util.format_time_long(6319),
        "~tracks": ngettext("%d track", "%d tracks", 5) % 5,
        "~discs": ngettext("%d disc", "%d discs", 2) % 2,
        "~#rating": 0.75,
        "album": _("An Example Album"),
        "~people": _SOME_PEOPLE + "..."})

    def __init__(self, browser):
        if self.is_not_unique():
            return
        super(Preferences, self).__init__()
        self.set_border_width(12)
        self.set_title(_("Cover Grid Preferences") + " - Quod Libet")
        self.set_default_size(420, 380)
        self.set_transient_for(qltk.get_top_parent(browser))
        # Do this config-driven setup at instance-time
        self._EXAMPLE_ALBUM["~rating"] = format_rating(0.75)

        box = Gtk.VBox(spacing=6)
        vbox = Gtk.VBox(spacing=6)
        cb = ConfigCheckButton(
            _("Show album _text"), "browsers", "album_text")
        cb.set_active(config.getboolean("browsers", "album_text"))
        cb.connect('toggled',
                   lambda s: browser.toggle_text())
        vbox.pack_start(cb, False, True, 0)

        row_spacing = config.getint("browsers", "row_spacing", 6)
        adj = Gtk.Adjustment.new(row_spacing, 0, 30, 1, 1, 0)
        rs_spin = Gtk.SpinButton(adjustment=adj)
        rs_spin.set_digits(0)
        rs_spin.set_numeric(True)
        rs_spin.connect('changed', self.__changed, 'browsers', 'row_spacing', browser)
        rs_label = Gtk.Label(label=_("_Row spacing:"))
        rs_label.set_use_underline(True)
        rs_label.set_mnemonic_widget(rs_spin)
        
        column_spacing = config.getint("browsers", "column_spacing", 6)
        adj = Gtk.Adjustment.new(column_spacing, 0, 30, 1, 1, 0)
        cs_spin = Gtk.SpinButton(adjustment=adj)
        cs_spin.set_digits(0)
        cs_spin.set_numeric(True)
        cs_spin.connect('changed', self.__changed, 'browsers', 'column_spacing', browser)
        cs_label = Gtk.Label(label=_("_Column spacing:"))
        cs_label.set_use_underline(True)
        cs_label.set_mnemonic_widget(cs_spin)
        
        item_padding = config.getint("browsers", "item_padding", 6)
        adj = Gtk.Adjustment.new(item_padding, 0, 30, 1, 1, 0)
        ip_spin = Gtk.SpinButton(adjustment=adj)
        ip_spin.set_digits(0)
        ip_spin.set_numeric(True)
        ip_spin.connect('changed', self.__changed, 'browsers', 'item_padding', browser)
        ip_label = Gtk.Label(label=_("_Item padding:"))
        ip_label.set_use_underline(True)
        ip_label.set_mnemonic_widget(ip_spin)

        # packing
        table = Gtk.Table.new(3, 3, False)
        table.set_col_spacings(6)
        table.set_row_spacings(6)

        rs_label.set_alignment(0, 0.5)
        table.attach(rs_label, 0, 1, 0, 1, xoptions=0)
        cs_label.set_alignment(0, 0.5)
        table.attach(cs_label, 0, 1, 1, 2, xoptions=0)
        ip_label.set_alignment(0, 0.5)
        table.attach(ip_label, 0, 1, 2, 3, xoptions=0)

        rs_align = Gtk.Alignment.new(0, 0.5, 0, 1)
        rs_align.add(rs_spin)
        table.attach(rs_align, 1, 2, 0, 1)

        cs_align = Gtk.Alignment.new(0, 0.5, 0, 1)
        cs_align.add(cs_spin)
        table.attach(cs_align, 1, 2, 1, 2)
        
        ip_align = Gtk.Alignment.new(0, 0.5, 0, 1)
        ip_align.add(ip_spin)
        table.attach(ip_align, 1, 2, 2, 3)

        vbox.pack_start(table, False, True, 0)

        f = qltk.Frame(_("Options"), child=vbox)
        box.pack_start(f, False, True, 12)

        vbox = Gtk.VBox(spacing=6)
        label = Gtk.Label()
        label.set_alignment(0.0, 0.5)
        label.set_padding(6, 6)
        eb = Gtk.EventBox()
        eb.get_style_context().add_class("entry")
        eb.add(label)

        edit = PatternEditBox(PATTERN)
        edit.text = browser._pattern_text
        edit.apply.connect('clicked',
                     self.__set_pattern, edit, browser)
        connect_obj(edit.buffer, 'changed',
                    self.__preview_pattern, edit, label)

        vbox.pack_start(eb, False, True, 3)
        vbox.pack_start(edit, True, True, 0)
        self.__preview_pattern(edit, label)
        f = qltk.Frame(_("Album Display"), child=vbox)
        box.pack_start(f, True, True, 0)

        main_box = Gtk.VBox(spacing=12)
        close = Gtk.Button(stock=Gtk.STOCK_CLOSE)
        close.connect('clicked', lambda *x: self.destroy())
        b = Gtk.HButtonBox()
        b.set_layout(Gtk.ButtonBoxStyle.END)
        b.pack_start(close, True, True, 0)

        main_box.pack_start(box, True, True, 0)
        self.use_header_bar()

        if not self.has_close_button():
            main_box.pack_start(b, False, True, 0)
        self.add(main_box)

        close.grab_focus()
        self.show_all()

    def __set_pattern(self, apply, edit, browser):
        browser.refresh_pattern(edit.text)

    def __preview_pattern(self, edit, label):
        try:
            text = XMLFromMarkupPattern(edit.text) % self._EXAMPLE_ALBUM
        except:
            text = _("Invalid pattern")
            edit.apply.set_sensitive(False)
        try:
            Pango.parse_markup(text, -1, u"\u0000")
        except GLib.GError:
            text = _("Invalid pattern")
            edit.apply.set_sensitive(False)
        else:
            edit.apply.set_sensitive(True)
        label.set_markup(text)

    def __changed(self, adj, section, name, browser):
        config.set(section, name, int(adj.get_value()))
        browser.refresh_view()
