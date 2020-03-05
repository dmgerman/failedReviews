#!/usr/bin/env python

import enum
import operator
import os
import re
import time
import types
import unicodedata
import urllib.parse
from functools import reduce

from aqt import mw
from aqt.utils import showInfo, showCritical
from aqt.webview import AnkiWebView
from aqt.qt import (Qt, QAction, QStandardPaths,
                    QImage, QPainter, QSize, QEvent, QSizePolicy,
                    QFileDialog, QDialog, QHBoxLayout, QVBoxLayout, QGroupBox,
                    QLineEdit, QLabel, QCheckBox, QSpinBox, QComboBox, QPushButton)

class FailedReviewsWebView(AnkiWebView):
    def __init__(self, parent=None):
        super().__init__()
        # Saved images are empty if the background is transparent; AnkiWebView
        # sets bg color to transparent by default
        self._page.setBackgroundColor(Qt.white)

class FailedReviews:
    def __init__(self, mw):
        # save the cursor
        if mw:
            self.menuAction = QAction("Failed Reviews", mw, triggered=self.setup)
            mw.form.menuTools.addSeparator()
            mw.form.menuTools.addAction(self.menuAction)

    def results(self, c, interval):
        # i don't get it why anki runs in a single transactions. This means that if the add-on breaks, it will
        # taking along the reviews of the user.
        # so let us commit. At this point, things should be "safe" for the user to have the reviews committed

        # we'll run in a transactions so we do not alter the database, easier than removing the tables
        c.execute("commit")

        c.execute("begin")

        # why compute in python when the database can do all the work with less potential for error?

        # note that the create reviews table receives as a parameter the interval
        # we could have used the current time, but it is probably more useful to use the time of last review

        c.execute("""
create table deckinfo as
        SELECT value as deckname,
        substr(substr(r.fullkey, 3), 0, instr(substr(r.fullkey, 3), '.'))  as did,
        r.fullkey from col, json_tree(col.decks) as r
        where r.key = 'name';
""")

        c.execute("create temp table reviews as select id from revlog where type = 1 and id > (select max(id) - ? * (60*60*24*1000) from revlog);", int(interval))

        c.execute("""
create temp table temp as
  select deckname, ord, ease, count(*) as count, count(distinct cid) as ccount
     from
   reviews natural join revlog
   join cards c on(c.id = cid) join deckinfo d using (did)
   group by deckname, ord, ease;
-- combine them so we can easily compute the proportion
""")

        r = c.all("""
select *, ok*1.0/(ok + failed) as prop from
(select deckname, ord, ccount as cfailed, count as failed from temp where ease = 1) natural join
(select deckname, ord, ccount as cok, count as ok from temp where ease = 3);
""")
        c.execute("rollback")
        return r

    def compute(self, config):

        self.win = QDialog(mw)
        self.wv = FailedReviewsWebView()
        vl = QVBoxLayout()
        vl.setContentsMargins(0, 0, 0, 0)
        vl.addWidget(self.wv)
        r = self.results(config.cursor, config.interval)

        header = """<tr>
<td><b>Deck</b></td>
<td><b>Card type</b></td>
<td><b>Cards failed</b></td>
<td><b>Reviews failed</b></td>
<td><b>Cards Ok</b></td>
<td><b>Reviews ok</b></td>
<td><b>Proportion</b></td></tr>
"""
        mystr = "<tr>"+ "</tr><br><tr>".join("<td>" +  "</td><td>".join(str(col) for col in tuple) + "</td>" for tuple in r ) + "</tr>"
        self.html = "<h2>Results for reviews of failed cards within last " + str(config.interval) + " days since last review</h2>\n"  + "<table>" + header + mystr + "</table>"

        self.wv.stdHtml(self.html)
        hl = QHBoxLayout()
        vl.addLayout(hl)
        bb = QPushButton("Close", clicked=self.win.reject)
        hl.addWidget(bb)
        self.win.setLayout(vl)
        self.win.resize(800, 400)

        return 0



    def setup(self):
        addonconfig = mw.addonManager.getConfig(__name__)
        config = types.SimpleNamespace(**addonconfig['defaults'])
        config.cursor = mw.col.db

        swin = QDialog(mw)

        vl = QVBoxLayout()
        fl = QHBoxLayout()
        frm = QGroupBox("Settings")
        vl.addWidget(frm)
        il = QVBoxLayout()
        fl = QHBoxLayout()
        stint = QSpinBox()
        stint.setRange(1, 65536)
        stint.setValue(config.interval)
        il.addWidget(QLabel("Days of interval (note that this is the number of days since the last review, not today):"))
        il.addWidget(stint)
        frm.setLayout(il)

        hl = QHBoxLayout()
        vl.addLayout(hl)
        gen = QPushButton("Generate", clicked=swin.accept)
        hl.addWidget(gen)
        cls = QPushButton("Close", clicked=swin.reject)
        hl.addWidget(cls)
        swin.setLayout(vl)
        swin.setTabOrder(gen, cls)
        swin.setTabOrder(stint, gen)
        swin.resize(500, 200)
        if swin.exec_():
            mw.progress.start(immediate=True)
            config.interval = stint.value()
            self.compute(config)
            mw.progress.finish()
            self.win.show()

if __name__ != "__main__":
    if mw:
        mw.failedreviews = FailedReviews(mw)
else:
    print("This is an addon for the Anki spaced repetition learning system and cannot be run directly.")
    print("Please download Anki from <http://ankisrs.net/>")

# vim:expandtab:
