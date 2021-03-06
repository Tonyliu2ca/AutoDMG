#-*- coding: utf-8 -*-
#
#  IEDProfileController.py
#  AutoDMG
#
#  Created by Per Olofsson on 2013-10-21.
#  Copyright (c) 2013 Per Olofsson, University of Gothenburg. All rights reserved.
#

from AppKit import *
from Foundation import *
from objc import IBOutlet

import os.path
from collections import defaultdict
from IEDLog import *


class IEDProfileController(NSObject):
    """Keep track of update profiles, containing lists of the latest updates
    needed to build a fully updated OS X image."""
    
    profileUpdateWindow = IBOutlet()
    progressBar = IBOutlet()
    delegate = IBOutlet()
    
    def awakeFromNib(self):
        # Save the path to UpdateProfiles.plist in the user's application
        # support directory.
        fm = NSFileManager.defaultManager()
        url, error = fm.URLForDirectory_inDomain_appropriateForURL_create_error_(NSApplicationSupportDirectory,
                                                                                 NSUserDomainMask,
                                                                                 None,
                                                                                 True,
                                                                                 None)
        self.userUpdateProfilesPath = os.path.join(url.path(), u"AutoDMG", u"UpdateProfiles.plist")
        
        # Load UpdateProfiles from the application bundle.
        bundleUpdateProfilesPath = NSBundle.mainBundle().pathForResource_ofType_(u"UpdateProfiles", u"plist")
        bundleUpdateProfiles = NSDictionary.dictionaryWithContentsOfFile_(bundleUpdateProfilesPath)
        
        latestProfiles = self.updateUsersProfilesIfNewer_(bundleUpdateProfiles)
        # Load the profiles.
        self.loadProfilesFromPlist_(latestProfiles)
    
    def profileForVersion_Build_(self, version, build):
        """Return the update profile for a certain OS X version and build."""
        
        try:
            profile = self.profiles[u"%s-%s" % (version, build)]
            LogNotice(u"Update profile for %@ %@: %@", version, build, u", ".join(u[u"name"] for u in profile))
        except KeyError:
            profile = None
            LogNotice(u"No update profile for %@ %@", version, build)
        return profile
    
    def whyNoProfileForVersion_build_(self, whyVersion, whyBuild):
        """Given a version and build that doesn't have a profile, try to
        provide a helpful explanation as to why that might be."""
        
        # Check if it has been deprecated.
        try:
            replacement = self.deprecatedInstallerBuilds[whyBuild]
            version, _, build = replacement.partition(u"-")
            return u"Installer deprecated by %s %s" % (version, build)
        except KeyError:
            pass
        
        whyVersionTuple = tuple(int(x) for x in whyVersion.split(u"."))
        whyMajor = whyVersionTuple[1]
        whyPoint = whyVersionTuple[2] if len(whyVersionTuple) > 2 else None
        
        buildsForVersion = defaultdict(set)
        supportedMajorVersions = set()
        supportedPointReleases = defaultdict(set)
        for versionBuild in self.profiles.keys():
            version , _, build = versionBuild.partition(u"-")
            buildsForVersion[version].add(build)
            versionTuple = tuple(int(x) for x in version.split(u"."))
            major = versionTuple[1]
            supportedMajorVersions.add(major)
            point = versionTuple[2] if len(versionTuple) > 2 else None
            supportedPointReleases[major].add(point)
        
        if whyMajor not in supportedMajorVersions:
            return "10.%d is not supported" % whyMajor
        elif whyVersion in buildsForVersion:
            return u"Unknown build %s" % whyBuild
        else:
            # It's a supported OS X version, but we don't have a profile for
            # this point release. Try to figure out if that's because it's too
            # old or too new.
            pointReleases = supportedPointReleases[whyMajor]
            oldestSupportedPointRelease = sorted(pointReleases)[0]
            newestSupportedPointRelease = sorted(pointReleases)[-1]
            if whyPoint < oldestSupportedPointRelease:
                return u"Deprecated installer"
            elif whyPoint > newestSupportedPointRelease:
                # If it's newer than any known release, just assume that we're
                # behind on updates and that all is well.
                return None
            else:
                # Well this is awkward.
                return u"Deprecated installer"
    
    def updateUsersProfilesIfNewer_(self, plist):
        """Update the user's update profiles if plist is newer. Returns
           whichever was the newest."""
        
        # Load UpdateProfiles from the user's application support directory.
        userUpdateProfiles = NSDictionary.dictionaryWithContentsOfFile_(self.userUpdateProfilesPath)
        
        # If the bundle's plist is newer, update the user's.
        if (not userUpdateProfiles) or (userUpdateProfiles[u"PublicationDate"].timeIntervalSinceDate_(plist[u"PublicationDate"]) < 0):
            LogDebug(u"Saving updated UpdateProfiles.plist")
            self.saveUsersProfiles_(plist)
            return plist
        else:
            return userUpdateProfiles
    
    def saveUsersProfiles_(self, plist):
        """Save UpdateProfiles.plist to application support."""
        
        LogInfo(u"Saving update profiles with PublicationDate %@", plist[u"PublicationDate"])
        if not plist.writeToFile_atomically_(self.userUpdateProfilesPath, False):
            LogError(u"Failed to write %@", self.userUpdateProfilesPath)
    
    def loadProfilesFromPlist_(self, plist):
        """Load UpdateProfiles from a plist dictionary."""
        
        self.profiles = dict()
        for name, updates in plist[u"Profiles"].iteritems():
            profile = list()
            for update in updates:
                profile.append(plist[u"Updates"][update])
            self.profiles[name] = profile
        self.publicationDate = plist[u"PublicationDate"]
        self.updatePaths = dict()
        for name, update in plist[u"Updates"].iteritems():
            self.updatePaths[update[u"sha1"]] = os.path.basename(update[u"url"])
        self.deprecatedInstallerBuilds = dict()
        if u"DeprecatedInstallers" in plist:
            for replacement, builds in plist[u"DeprecatedInstallers"].iteritems():
                for build in builds:
                    self.deprecatedInstallerBuilds[build] = replacement
        if self.delegate:
            self.delegate.profilesUpdated()
    
    # FIXME: use a delegate protocol instead.
    def updateFromURL_withTarget_selector_(self, url, target, selector):
        """Download the latest update profiles asynchronously and notify
           target with the result."""
        
        self.profileUpdateWindow.makeKeyAndOrderFront_(self)
        self.progressBar.startAnimation_(self)
        self.performSelectorInBackground_withObject_(self.updateInBackground_, [url, target, selector])
    
    # Continue in background thread.
    def updateInBackground_(self, args):
        url, target, selector = args
        request = NSURLRequest.requestWithURL_(url)
        data, response, error = NSURLConnection.sendSynchronousRequest_returningResponse_error_(request, None, None)
        self.profileUpdateWindow.orderOut_(self)
        if not data:
            message = u"Failed to download %s: %s" % (url.absoluteString(), error.localizedDescription())
            self.failUpdate_withTarget_selector_(message, target, selector)
            return
        if response.statusCode() != 200:
            self.failUpdate_withTarget_selector_(u"Update server responded with code %d.", response.statusCode(), target, selector)
            return
        plist, format, error = NSPropertyListSerialization.propertyListWithData_options_format_error_(data,
                                                                                                      NSPropertyListImmutable,
                                                                                                      None,
                                                                                                      None)
        if not plist:
            self.failUpdate_withTarget_selector_(u"Couldn't decode update data.", target, selector)
            return
        LogNotice(u"Downloaded update profiles with PublicationDate %@", plist[u"PublicationDate"])
        latestProfiles = self.updateUsersProfilesIfNewer_(plist)
        self.loadProfilesFromPlist_(latestProfiles)
        dateFormatter = NSDateFormatter.alloc().init()
        timeZone = NSTimeZone.timeZoneWithName_(u"UTC")
        dateFormatter.setTimeZone_(timeZone)
        dateFormatter.setDateFormat_(u"yyyy-MM-dd HH:mm:ss")
        dateString = dateFormatter.stringFromDate_(latestProfiles[u"PublicationDate"])
        message = u"Using update profiles from %s UTC" % dateString
        self.succeedUpdate_WithTarget_selector_(message, target, selector)
    
    def failUpdate_withTarget_selector_(self, error, target, selector):
        """Notify target of a failed update."""
        
        LogError(u"Profile update failed: %@", error)
        if target:
            target.performSelectorOnMainThread_withObject_waitUntilDone_(selector,
                                                                         {u"success": False,
                                                                          u"error-message": error},
                                                                         False)
    
    def succeedUpdate_WithTarget_selector_(self, message, target, selector):
        """Notify target of a successful update."""
        
        if target:
            target.performSelectorOnMainThread_withObject_waitUntilDone_(selector,
                                                                         {u"success": True,
                                                                          u"message": message},
                                                                         False)

