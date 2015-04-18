# -*- coding: utf-8 -*-
# Copyright 2004-2007 Joe Wreschnig, Michael Urman, Iñigo Serna
#           2009-2010 Steven Robertson
#           2012-2013 Nick Boultbee
#           2009-2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from __future__ import absolute_import

import os

from gi.repository import Gtk, Pango, Gdk, GLib, Gio

from .prefs import Preferences, PATTERN
from quodlibet.browsers.albums.models import AlbumModel, AlbumFilterModel, AlbumSortModel
from quodlibet.browsers.albums.main import VisibleUpdate

from quodlibet import config
from quodlibet import const
from quodlibet import qltk
from quodlibet import util

from quodlibet.browsers._base import Browser
from quodlibet.query import Query
from quodlibet.pattern import XMLFromMarkupPattern
from quodlibet.qltk.completion import EntryWordCompletion
from quodlibet.qltk.information import Information
from quodlibet.qltk.properties import SongProperties
from quodlibet.qltk.songsmenu import SongsMenu
from quodlibet.qltk.views import AllTreeView
from quodlibet.qltk.x import MenuItem, Align, ScrolledWindow, RadioMenuItem
from quodlibet.qltk.x import SymbolicIconImage
from quodlibet.qltk.searchbar import SearchBarBox
from quodlibet.qltk.menubutton import MenuButton
from quodlibet.util import copool, connect_destroy
from quodlibet.util.library import background_filter
from quodlibet.util import connect_obj, DeferredSignal
from quodlibet.util.collection import Album
from quodlibet.qltk.cover import get_no_cover_pixbuf
from quodlibet.qltk.image import (get_pbosf_for_pixbuf, get_scale_factor,
    set_renderer_from_pbosf, add_border_widget)


PATTERN_FN = os.path.join(const.USERDIR, "album_pattern")


class AlbumTagCompletion(EntryWordCompletion):
    def __init__(self):
        super(AlbumTagCompletion, self).__init__()
        try:
            model = self.__model
        except AttributeError:
            model = type(self).__model = Gtk.ListStore(str)
            self.__refreshmodel()
        self.set_model(model)
        self.set_text_column(0)

    def __refreshmodel(self, *args):
        for tag in ["title", "album", "date", "people", "artist", "genre"]:
            self.__model.append(row=[tag])
        for tag in ["tracks", "discs", "length", "date"]:
            self.__model.append(row=["#(" + tag])
        for tag in ["rating", "playcount", "skipcount"]:
            for suffix in ["avg", "max", "min", "sum"]:
                self.__model.append(row=["#(%s:%s" % (tag, suffix)])


def cmpa(a, b):
    """Like cmp but treats values that evaluate to false as inf"""
    if not a and b:
        return 1
    if not b and a:
        return -1
    return cmp(a, b)


def compare_title(a1, a2):
    # all albums has to stay at the top
    if (a1 and a2) is None:
        return cmp(a1, a2)
    # move album without a title to the bottom
    if not a1.title:
        return 1
    if not a2.title:
        return -1
    return (cmpa(a1.sort, a2.sort) or
            cmp(a1.key, a2.key))


def compare_artist(a1, a2):
    if (a1 and a2) is None:
        return cmp(a1, a2)
    if not a1.title:
        return 1
    if not a2.title:
        return -1
    return (cmpa(a1.peoplesort, a2.peoplesort) or
            cmpa(a1.date, a2.date) or
            cmpa(a1.sort, a2.sort) or
            cmp(a1.key, a2.key))


def compare_date(a1, a2):
    if (a1 and a2) is None:
        return cmp(a1, a2)
    if not a1.title:
        return 1
    if not a2.title:
        return -1
    return (cmpa(a1.date, a2.date) or
            cmpa(a1.sort, a2.sort) or
            cmp(a1.key, a2.key))


def compare_genre(a1, a2):
    if (a1 and a2) is None:
        return cmp(a1, a2)
    if not a1.title:
        return 1
    if not a2.title:
        return -1
    return (cmpa(a1.genre, a2.genre) or
            cmpa(a1.peoplesort, a2.peoplesort) or
            cmpa(a1.date, a2.date) or
            cmpa(a1.sort, a2.sort) or
            cmp(a1.key, a2.key))


def compare_rating(a1, a2):
    if (a1 and a2) is None:
        return cmp(a1, a2)
    if not a1.title:
        return 1
    if not a2.title:
        return -1
    return (-cmp(a1("~#rating"), a2("~#rating")) or
            cmpa(a1.date, a2.date) or
            cmpa(a1.sort, a2.sort) or
            cmp(a1.key, a2.key))


class PreferencesButton(Gtk.HBox):
    def __init__(self, browser, model):
        super(PreferencesButton, self).__init__()

        sort_orders = [
            (_("_Title"), self.__compare_title),
            (_("_Artist"), self.__compare_artist),
            (_("_Date"), self.__compare_date),
            (_("_Genre"), self.__compare_genre),
            (_("_Rating"), self.__compare_rating),
        ]

        menu = Gtk.Menu()

        sort_item = Gtk.MenuItem(
            label=_(u"Sort _by…"), use_underline=True)
        sort_menu = Gtk.Menu()

        active = config.getint('browsers', 'album_sort', 1)

        item = None
        for i, (label, func) in enumerate(sort_orders):
            item = RadioMenuItem(group=item, label=label,
                                 use_underline=True)
            model.set_sort_func(100 + i, func)
            if i == active:
                model.set_sort_column_id(100 + i, Gtk.SortType.ASCENDING)
                item.set_active(True)
            item.connect("toggled",
                         util.DeferredSignal(self.__sort_toggled_cb),
                         model, i)
            sort_menu.append(item)

        sort_item.set_submenu(sort_menu)
        menu.append(sort_item)

        pref_item = MenuItem(_("_Preferences"), Gtk.STOCK_PREFERENCES)
        menu.append(pref_item)
        connect_obj(pref_item, "activate", Preferences, browser)

        menu.show_all()

        button = MenuButton(
                SymbolicIconImage("emblem-system", Gtk.IconSize.MENU),
                arrow=True)
        button.set_menu(menu)
        self.pack_start(button, True, True, 0)

    def __sort_toggled_cb(self, item, model, num):
        if item.get_active():
            config.set("browsers", "album_sort", str(num))
            model.set_sort_column_id(100 + num, Gtk.SortType.ASCENDING)

    def __compare_title(self, model, i1, i2, data):
        a1, a2 = model.get_value(i1), model.get_value(i2)
        return compare_title(a1, a2)

    def __compare_artist(self, model, i1, i2, data):
        a1, a2 = model.get_value(i1), model.get_value(i2)
        return compare_artist(a1, a2)

    def __compare_date(self, model, i1, i2, data):
        a1, a2 = model.get_value(i1), model.get_value(i2)
        return compare_date(a1, a2)

    def __compare_genre(self, model, i1, i2, data):
        a1, a2 = model.get_value(i1), model.get_value(i2)
        return compare_genre(a1, a2)

    def __compare_rating(self, model, i1, i2, data):
        a1, a2 = model.get_value(i1), model.get_value(i2)
        return compare_rating(a1, a2)


class CoverGrid(Browser, util.InstanceTracker, VisibleUpdate):
    __gsignals__ = Browser.__gsignals__
    __model = None
    __last_render = None
    __last_render_pb = None

    name = _("Cover Grid")
    accelerated_name = _("_Cover Grid")
    priority = 4

    def pack(self, songpane):
        container = qltk.ConfigRVPaned("browsers", "covergrid_pos", 0.4)
        container.pack1(self, True, False)
        container.pack2(songpane, True, False)
        return container

    def unpack(self, container, songpane):
        container.remove(songpane)
        container.remove(self)

    @classmethod
    def init(klass, library):
        try:
            klass._pattern_text = file(PATTERN_FN).read().rstrip()
        except EnvironmentError:
            klass._pattern_text = PATTERN

        klass._pattern = XMLFromMarkupPattern(klass._pattern_text)

    @classmethod
    def _destroy_model(klass):
        klass.__model.destroy()
        klass.__model = None

    @classmethod
    def toggle_text(klass):
        on = config.getboolean("browsers", "album_text")
        for covergrid in klass.instances():
            covergrid.__text_cells.set_visible(on)
            covergrid.view.queue_resize()
    
    @classmethod
    def refresh_view(klass):
        for covergrid in klass.instances():
            covergrid.view.set_row_spacing(config.getint("browsers", "row_spacing"))
            covergrid.view.set_column_spacing(config.getint("browsers", "column_spacing"))
            covergrid.view.set_item_padding(config.getint("browsers", "item_padding"))
            covergrid.view.queue_resize()

    @classmethod
    def refresh_pattern(klass, pattern_text):
        if pattern_text == klass._pattern_text:
            return
        klass._pattern_text = pattern_text
        klass._pattern = XMLFromMarkupPattern(pattern_text)
        klass.__model.refresh_all()
        pattern_fn = PATTERN_FN
        f = file(pattern_fn, "w")
        f.write(pattern_text + "\n")
        f.close()

    @classmethod
    def _init_model(klass, library):
        klass.__model = AlbumModel(library)
        klass.__library = library

    @classmethod
    def _refresh_albums(klass, albums):
        """We signal all other open album views that we changed something
        (Only needed for the cover atm) so they redraw as well."""
        if klass.__library:
            klass.__library.albums.refresh(albums)

    @util.cached_property
    def _no_cover(self):
        """Returns a cairo surface of pixbuf representing a missing cover"""

        cover_size = Album.COVER_SIZE
        scale_factor = get_scale_factor(self)
        pb = get_no_cover_pixbuf(cover_size, cover_size, scale_factor)
        return get_pbosf_for_pixbuf(self, pb)

    def __init__(self, library):
        super(CoverGrid, self).__init__(spacing=6)
        self.set_orientation(Gtk.Orientation.VERTICAL)

        self._register_instance()
        if self.__model is None:
            self._init_model(library)

        self._cover_cancel = Gio.Cancellable.new()

        self.scrollwin = sw = ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.IN)
        model_sort = AlbumSortModel(model=self.__model)
        model_filter = AlbumFilterModel(child_model=model_sort)
        self.view = view = Gtk.IconView(model_filter)
        #view.set_item_width(Album.COVER_SIZE + 12)
        self.view.set_row_spacing(config.getint("browsers", "row_spacing", 6))
        self.view.set_column_spacing(config.getint("browsers", "column_spacing", 6))
        self.view.set_item_padding(config.getint("browsers", "item_padding", 6))
        self.view.set_has_tooltip(True)
        self.view.connect("query-tooltip", self._show_tooltip)
        
        self.__bg_filter = background_filter()
        self.__filter = None
        model_filter.set_visible_func(self.__parse_query)

        render = Gtk.CellRendererPixbuf()
        render.set_property('width', Album.COVER_SIZE + 8)
        render.set_property('height', Album.COVER_SIZE + 8)
        view.pack_start(render, False)

        def cell_data_pb(view, cell, model, iter_, no_cover):
            album = model.get_album(iter_)

            if album is None:
                pixbuf = None
            elif album.cover:
                pixbuf = album.cover
                round_ = config.getboolean("albumart", "round")
                pixbuf = add_border_widget(
                    pixbuf, self.view, cell, round_)
                pixbuf = get_pbosf_for_pixbuf(self, pixbuf)
                # don't cache, too much state has an effect on the result
                self.__last_render_pb = None
            else:
                pixbuf = no_cover

            if self.__last_render_pb == pixbuf:
                return
            self.__last_render_pb = pixbuf
            set_renderer_from_pbosf(cell, pixbuf)

        view.set_cell_data_func(render, cell_data_pb, self._no_cover)

        self.__text_cells = render = Gtk.CellRendererText()
        render.set_visible(config.getboolean("browsers", "album_text"))
        render.set_property('alignment', Pango.Alignment.CENTER)
        render.set_property('ellipsize', Pango.EllipsizeMode.END)
        view.pack_start(render, False)

        def cell_data(view, cell, model, iter_, data):
            album = model.get_album(iter_)

            if album is None:
                text = "<b>%s</b>" % _("All Albums")
                text += "\n" + ngettext("%d album", "%d albums",
                        len(model) - 1) % (len(model) - 1)
                markup = text
            else:
                markup = CoverGrid._pattern % album

            if self.__last_render == markup:
                return
            self.__last_render = markup
            cell.markup = markup
            cell.set_property('markup', markup)

        view.set_cell_data_func(render, cell_data, None)

        view.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(view)

        view.connect('item-activated', self.__play_selection, None)

        self.__sig = connect_destroy(
            view, 'selection-changed',
            util.DeferredSignal(self.__update_songs, owner=self))

        targets = [("text/x-quodlibet-songs", Gtk.TargetFlags.SAME_APP, 1),
                   ("text/uri-list", 0, 2)]
        targets = [Gtk.TargetEntry.new(*t) for t in targets]

        view.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, targets, Gdk.DragAction.COPY)
        view.connect("drag-data-get", self.__drag_data_get)
        connect_obj(view, 'popup-menu', self.__popup, view, library)

        self.accelerators = Gtk.AccelGroup()
        search = SearchBarBox(completion=AlbumTagCompletion(),
                              accel_group=self.accelerators)
        search.connect('query-changed', self.__update_filter)
        connect_obj(search, 'focus-out', lambda w: w.grab_focus(), view)
        self.__search = search

        prefs = PreferencesButton(self, model_sort)
        search.pack_start(prefs, False, True, 0)
        self.pack_start(Align(search, left=6, top=6), False, True, 0)
        self.pack_start(sw, True, True, 0)

        self.connect("destroy", self.__destroy)
        
        self.enable_row_update(view, sw, self.view)

        self.connect('key-press-event', self.__key_pressed, library.librarian)

        self.show_all()

    def __key_pressed(self, widget, event, librarian):
        if qltk.is_accel(event, "<ctrl>I"):
            songs = self.__get_selected_songs()
            if songs:
                window = Information(librarian, songs, self)
                window.show()
            return True
        elif qltk.is_accel(event, "<alt>Return"):
            songs = self.__get_selected_songs()
            if songs:
                window = SongProperties(librarian, songs, self)
                window.show()
            return True
        return False

    def _row_needs_update(self, model, iter_):
        album = model.get_album(iter_)
        return album is not None and not album.scanned

    def _update_row(self, filter_model, iter_):
        sort_model = filter_model.get_model()
        model = sort_model.get_model()
        iter_ = filter_model.convert_iter_to_child_iter(iter_)
        iter_ = sort_model.convert_iter_to_child_iter(iter_)
        tref = Gtk.TreeRowReference.new(model, model.get_path(iter_))

        def callback():
            path = tref.get_path()
            if path is not None:
                model.row_changed(path, model.get_iter(path))
            # XXX: icon view seems to ignore row_changed signals for pixbufs..
            self.queue_resize()

        album = model.get_album(iter_)
        scale_factor = get_scale_factor(self)
        album.scan_cover(scale_factor=scale_factor,
                         callback=callback,
                         cancel=self._cover_cancel)

    def __destroy(self, browser):
        self._cover_cancel.cancel()
        self.disable_row_update()

        self.view.set_model(None)

        klass = type(browser)
        if not klass.instances():
            klass._destroy_model()

    def __update_filter(self, entry, text, scroll_up=True, restore=False):
        model = self.view.get_model()

        self.__filter = None
        if not Query.match_all(text):
            self.__filter = Query(text, star=["~people", "album"]).search
        self.__bg_filter = background_filter()

        self.__inhibit()

        # don't filter on restore if there is nothing to filter
        if not restore or self.__filter or self.__bg_filter:
            model.refilter()

        self.__uninhibit()

    def __parse_query(self, model, iter_, data):
        f, b = self.__filter, self.__bg_filter

        if f is None and b is None:
            return True
        else:
            album = model.get_album(iter_)
            if album is None:
                return True
            elif b is None:
                return f(album)
            elif f is None:
                return b(album)
            else:
                return b(album) and f(album)

    def __popup(self, view, event, library):
        x = int(event.x)
        y = int(event.y)
        current_path = view.get_path_at_pos(x, y)
        if event.button == Gdk.BUTTON_SECONDARY and current_path:
            if not view.path_is_selected(current_path):
                view.unselect_all()
            view.select_path(current_path)
            albums = self.__get_selected_albums()
            songs = self.__get_songs_from_albums(albums)

            items = []
            num = len(albums)
            button = MenuItem(
                ngettext("Reload album _cover", "Reload album _covers", num),
                Gtk.STOCK_REFRESH)
            button.connect('activate', self.__refresh_album, view)
            items.append(button)

            menu = SongsMenu(library, songs, items=[items])
            menu.show_all()
            menu.popup(None, None, None, event.button, event.time, Gtk.get_current_event_time())

    def _show_tooltip(self, widget, x, y, keyboard_tip, tooltip):
        w = self.scrollwin.get_hadjustment().get_value()
        z = self.scrollwin.get_vadjustment().get_value()
        path = widget.get_path_at_pos(int(x + w), int(y + z))
        if path is None:
            return False
        model = widget.get_model()
        iter = model.get_iter(path)
        album = model.get_album(iter)
        if album is None:
            text = "<b>%s</b>" % _("All Albums")
            text += "\n" + ngettext("%d album", "%d albums", len(model) - 1) % (len(model) - 1)
            markup = text
        else:
            markup = CoverGrid._pattern % album
        tooltip.set_markup(markup)
        return True

    def __refresh_album(self, menuitem, view):
        albums = self.__get_selected_albums()
        for album in albums:
            album.scan_cover(True)
        self._refresh_albums(albums)

    def __get_selected_albums(self):
        model = self.view.get_model()
        paths = self.view.get_selected_items()
        return model.get_albums(paths)

    def __get_songs_from_albums(self, albums, sort=True):
        # Sort first by how the albums appear in the model itself,
        # then within the album using the default order.
        songs = []
        if sort:
            for album in albums:
                songs.extend(sorted(album.songs, key=lambda s: s.sort_key))
        else:
            for album in albums:
                songs.extend(album.songs)
        return songs

    def __get_selected_songs(self, sort=True):
        albums = self.__get_selected_albums()
        return self.__get_songs_from_albums(albums, sort)

    def __drag_data_get(self, view, ctx, sel, tid, etime):
        songs = self.__get_selected_songs()
        if tid == 1:
            qltk.selection_set_songs(sel, songs)
        else:
            sel.set_uris([song("~uri") for song in songs])

    def __play_selection(self, view, indices, col):
        self.songs_activated()

    def active_filter(self, song):
        for album in self.__get_selected_albums():
            if song in album.songs:
                return True
        return False

    def can_filter_text(self):
        return True

    def filter_text(self, text):
        self.__search.set_text(text)
        if Query.is_parsable(text):
            self.__update_filter(self.__search, text)
            self.__inhibit()
            self.view.set_cursor((0,))
            self.__uninhibit()
            self.activate()

    def can_filter(self, key):
        # numerics are different for collections, and title
        # works, but not of much use here
        if key is not None and (key.startswith("~#") or key == "title"):
            return False
        return super(CoverGrid, self).can_filter(key)

    def can_filter_albums(self):
        return True

    def list_albums(self):
        model = self.view.get_model()
        return [row[0].key for row in model if row[0]]

    def filter_albums(self, values):
        view = self.view
        self.__inhibit()
        changed = view.select_by_func(lambda r: r[0] and r[0].key in values)
        self.__uninhibit()
        if changed:
            self.activate()

    def unfilter(self):
        self.filter_text("")
        self.view.set_cursor((0,))

    def activate(self):
        self.view.emit('selection-changed')

    def __inhibit(self):
        self.view.handler_block(self.__sig)

    def __uninhibit(self):
        self.view.handler_unblock(self.__sig)

    def restore(self):
        text = config.get("browsers", "query_text").decode("utf-8")
        #entry = self.__search
        #entry.set_text(text)

        # update_filter expects a parsable query
        #if Query.is_parsable(text):
        #    self.__update_filter(entry, text, scroll_up=False, restore=True)

        keys = config.get("browsers", "albums").split("\n")

    def scroll(self, song):
        album_key = song.album_key
        select = lambda r: r[0] and r[0].key == album_key
        self.view.select_by_func(select, one=True)

    def __get_config_string(self):
        model = self.view.get_model()
        paths = self.view.get_selected_items()

        # All is selected
        if model.contains_all(paths):
            return ""

        # All selected albums
        albums = model.get_albums(paths)

        confval = "\n".join((a.str_key for a in albums))
        # ConfigParser strips a trailing \n so we move it to the front
        if confval and confval[-1] == "\n":
            confval = "\n" + confval[:-1]
        return confval

    def save(self):
        conf = self.__get_config_string()
        config.set("browsers", "albums", conf)
        text = self.__search.get_text().encode("utf-8")
        config.set("browsers", "query_text", text)

    def __update_songs(self, selection):
        songs = self.__get_selected_songs(sort=False)
        self.songs_selected(songs)
