#-*- coding: utf-8 -*-
#
#  IEDLog.py
#  AutoDMG
#
#  Created by Per Olofsson on 2013-10-25.
#  Copyright (c) 2013 Per Olofsson, University of Gothenburg. All rights reserved.
#


from Foundation import *
from AppKit import *
from objc import IBAction, IBOutlet

from IEDLogLine import *
import inspect


IEDLogLevelEmergency = 0
IEDLogLevelAlert     = 1
IEDLogLevelCritical  = 2
IEDLogLevelError     = 3
IEDLogLevelWarning   = 4
IEDLogLevelNotice    = 5
IEDLogLevelInfo      = 6
IEDLogLevelDebug     = 7


defaults = NSUserDefaults.standardUserDefaults()


class IEDLog(NSObject):
    
    # Singleton instance.
    _instance = None
    
    logWindow = IBOutlet()
    logTableView = IBOutlet()
    levelSelector = IBOutlet()
    
    logLines = list()
    visibleLogLines = list()
    
    def init(self):
        # Initialize singleton.
        if IEDLog._instance is not None:
            return IEDLog._instance
        self = super(IEDLog, self).init()
        if self is None:
            return None
        IEDLog._instance = self
        self.logAtBottom = True
        return self
    
    def awakeFromNib(self):
        global defaults
        self.levelSelector.selectItemAtIndex_(defaults.integerForKey_(u"LogLevel"))
        self.logTableView.setDataSource_(self)
        nc = NSNotificationCenter.defaultCenter()
        nc.addObserver_selector_name_object_(self,
                                             self.logViewScrolled_,
                                             NSViewBoundsDidChangeNotification,
                                             self.logTableView.enclosingScrollView().contentView())
    
    # Helper methods.
    
    def levelName_(self, level):
        return (
            u"Emergency",
            u"Alert",
            u"Critical",
            u"Error",
            u"Warning",
            u"Notice",
            u"Info",
            u"Debug",
        )[level]
    
    def addMessage_level_(self, message, level):
        logLine = IEDLogLine.alloc().initWithMessage_level_(message, level)
        self.logLines.append(logLine)
        if defaults.integerForKey_(u"LogLevel") >= level:
            self.visibleLogLines.append(logLine)
            self.logTableView.reloadData()
            if self.logAtBottom:
                self.logTableView.scrollRowToVisible_(len(self.visibleLogLines) - 1)
    
    
    
    # Act on user showing log window.
    
    @IBAction
    def displayLogWindow_(self, sender):
        self.logAtBottom = True
        self.logTableView.scrollRowToVisible_(len(self.visibleLogLines) - 1)
        self.logWindow.makeKeyAndOrderFront_(self)
    
    
    
    # Act on notification for log being scrolled by user.
    
    def logViewScrolled_(self, notification):
        tableViewHeight = self.logTableView.bounds().size.height
        scrollView = self.logTableView.enclosingScrollView()
        scrollRect = scrollView.documentVisibleRect()
        scrollPos = scrollRect.origin.y + scrollRect.size.height
        
        if scrollPos >= tableViewHeight:
            self.logAtBottom = True
        else:
            self.logAtBottom = False
    
    # Act on user filtering log.
    
    @IBAction
    def setLevel_(self, sender):
        self.visibleLogLines = [x for x in self.logLines if x.level() <= self.levelSelector.indexOfSelectedItem()]
        self.logTableView.reloadData()
    
    
    
    # Act on user clicking save button.
    
    @IBAction
    def saveLog_(self, sender):
        panel = NSSavePanel.savePanel()
        panel.setExtensionHidden_(False)
        panel.setAllowedFileTypes_([u"log", u"txt"])
        formatter = NSDateFormatter.alloc().init()
        formatter.setDateFormat_(u"yyyy-MM-dd HH.mm")
        dateStr = formatter.stringFromDate_(NSDate.date())
        panel.setNameFieldStringValue_(u"AutoDMG %s" % dateStr)
        result = panel.runModal()
        if result != NSFileHandlingPanelOKButton:
            return
        
        exists, error = panel.URL().checkResourceIsReachableAndReturnError_(None)
        if exists:
            success, error = NSFileManager.defaultManager().removeItemAtURL_error_(panel.URL(), None)
            if not success:
                NSApp.presentError_(error)
                return
        
        success, error = NSData.data().writeToURL_options_error_(panel.URL(), 0, None)
        if not success:
            NSApp.presentError_(error)
            return
        
        fh, error = NSFileHandle.fileHandleForWritingToURL_error_(panel.URL(), None)
        if fh is None:
            NSAlert.alertWithError_(error).runModal()
            return
        formatter = NSDateFormatter.alloc().init()
        formatter.setDateFormat_(u"yyyy-MM-dd HH:mm:ss")
        for logLine in self.logLines:
            textLine = NSString.stringWithFormat_(u"%@ %@: %@\n",
                                                  formatter.stringFromDate_(logLine.date()),
                                                  self.levelName_(logLine.level()),
                                                  logLine.message())
            fh.writeData_(textLine.dataUsingEncoding_(NSUTF8StringEncoding))
        fh.closeFile()
    
    
    
    # We're an NSTableViewDataSource.
    
    def numberOfRowsInTableView_(self, tableView):
        return len(self.visibleLogLines)
    
    def tableView_objectValueForTableColumn_row_(self, tableView, column, row):
        if column.identifier() == u"date":
            return self.visibleLogLines[row].date()
        elif column.identifier() == u"level":
            return self.levelName_(self.visibleLogLines[row].level())
        elif column.identifier() == u"message":
            return self.visibleLogLines[row].message()


_log = IEDLog.alloc().init()

def LogMessage(level, message):
    global _log
    
    prefix = u""
    if level == IEDLogLevelDebug:
        for caller in inspect.stack()[1:]:
            modname = inspect.getmodule(caller[0]).__name__
            if modname == u"IEDLog":
                continue
            lineno = caller[2]
            prefix = u"(%s:%d) " % (modname, lineno)
            break
    
    for line in message.split(u"\n"):
        _log.addMessage_level_(prefix + line, level)
        if defaults.integerForKey_(u"LogLevel") >= level:
            NSLog(u"%@", prefix + line)

def LogDebug(*args):
    LogMessage(IEDLogLevelDebug, NSString.stringWithFormat_(*args))

def LogInfo(*args):
    LogMessage(IEDLogLevelInfo, NSString.stringWithFormat_(*args))

def LogNotice(*args):
    LogMessage(IEDLogLevelNotice, NSString.stringWithFormat_(*args))

def LogWarning(*args):
    LogMessage(IEDLogLevelWarning, NSString.stringWithFormat_(*args))

def LogError(*args):
    LogMessage(IEDLogLevelError, NSString.stringWithFormat_(*args))
