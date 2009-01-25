"""

    KeepNote
    
    Notebook data structure

"""

# python imports
import os, sys, shutil, time, re

# xml imports
import xml.dom.minidom as xmldom
import xml.dom
import xml.parsers.expat
from xml.sax.saxutils import escape


# keepnote imports
import keepnote.xmlobject as xmlo
from keepnote.listening import Listeners
from keepnote.timestamp import \
     DEFAULT_TIMESTAMP_FORMATS, \
     get_timestamp, \
     get_localtime, \
     get_str_timestamp
from keepnote import safefile


# constants
BLANK_NOTE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml"><body></body></html>
"""

XML_HEADER = """\
<?xml version="1.0" encoding="UTF-8"?>
"""

NOTEBOOK_FORMAT_VERSION = 2
ELEMENT_NODE = 1
NODE_META_FILE = "node.xml"
PAGE_DATA_FILE = "page.html"
PREF_FILE = "notebook.nbk"
NOTEBOOK_META_DIR = "__NOTEBOOK__"
TRASH_DIR = "__TRASH__"
TRASH_NAME = "Trash"
DEFAULT_PAGE_NAME = "New Page"
DEFAULT_DIR_NAME = "New Folder"
DEFAULT_FONT_FAMILY = "Sans"
DEFAULT_FONT_SIZE = 10
DEFAULT_FONT = "%s %d" % (DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE)

# content types
CONTENT_TYPE_PAGE = "text/xhtml+xml"
CONTENT_TYPE_TRASH = "application/x-notebook-trash"
CONTENT_TYPE_DIR = "application/x-notebook-dir"


# information sort constants
INFO_SORT_NONE, \
INFO_SORT_MANUAL, \
INFO_SORT_TITLE, \
INFO_SORT_CREATED_TIME, \
INFO_SORT_MODIFIED_TIME = range(5)


#=============================================================================
# filename creation functions

REGEX_SLASHES = re.compile(r"[/\\]")
REGEX_BAD_CHARS = re.compile(r"[\?'&<>|`:;]")

def get_valid_filename(filename, default="folder"):
    """Converts a filename into a valid one
    
    Strips bad characters from filename
    """
    
    filename = re.sub(REGEX_SLASHES, "-", filename)
    filename = re.sub(REGEX_BAD_CHARS, "", filename)
    filename = filename.replace("\t", " ")
    filename = filename.strip(" \t.")
    
    # don't allow files to start with two underscores
    if filename.startswith("__"):
        filename = filename[2:]
    
    # don't allow pure whitespace filenames
    if filename == "":
        filename = default
    
    # use only lower case, some filesystems have trouble with mixed case
    filename = filename.lower()
    
    return filename
    

def get_unique_filename(path, filename, ext="", sep=" ", number=2):
    """Returns a unique version of a filename for a given directory"""

    if path != "":
        assert os.path.exists(path), path
    
    # try the given filename
    newname = os.path.join(path, filename + ext)
    if not os.path.exists(newname):
        return newname
    
    # try numbered suffixes
    i = number
    while True:
        newname = os.path.join(path, filename + sep + str(i) + ext)
        if not os.path.exists(newname):
            return newname
        i += 1


def get_valid_unique_filename(path, filename, ext="", sep=" ", number=2):
    """Returns a valid and unique version of a filename for a given path"""
    return get_unique_filename(path, get_valid_filename(filename), 
                               ext, sep, number)
    

def get_unique_filename_list(filenames, filename, ext="", sep=" ", number=2):
    """Returns a unique filename for a given list of existing files"""
    filenames = set(filenames)
    
    # try the given filename
    newname = filename + ext
    if newname not in filenames:
        return newname
    
    # try numbered suffixes
    i = number
    while True:
        newname = filename + sep + str(i) + ext
        if newname not in filenames:
            return newname
        i += 1


#=============================================================================
# File naming scheme


def get_node_meta_file(nodepath):
    """Returns the metadata file for a node"""
    return os.path.join(nodepath, NODE_META_FILE)

def get_page_data_file(pagepath):
    """Returns the HTML data file for a page"""
    return os.path.join(pagepath, PAGE_DATA_FILE)

def get_pref_file(nodepath):
    """Returns the filename of the notebook preference file"""
    return os.path.join(nodepath, PREF_FILE)

def get_pref_dir(nodepath):
    """Returns the directory of the notebook preference file"""
    return os.path.join(nodepath, NOTEBOOK_META_DIR)

def get_trash_dir(nodepath):
    """Returns the trash directory of the notebook"""
    return os.path.join(nodepath, TRASH_DIR)


#=============================================================================
# HTML functions

TAG_PATTERN = re.compile("<[^>]*>")
def strip_tags(line):
    return re.sub(TAG_PATTERN, "", line)

def read_data_as_plain_text(infile):
    """Read a Note data file as plain text"""

    for line in infile:
        # skip until body tag
        if "<body>" in line:
            pos = line.find("<body>")
            if pos != -1:
                yield strip_tags(line[pos+6:])
                break

    # yield until </body>
    for line in infile:
        pos = line.find("</body>")
        if pos != -1:
            yield strip_tags(line[:pos])
            break

        # strip tags
        yield strip_tags(line)


#=============================================================================
# functions


def get_notebook_version(filename):
    """Read the version of a notebook from its preference file"""
    
    if os.path.isdir(filename):
        filename = get_pref_file(filename)

    pref = NoteBookPreferences()

    try:
        g_notebook_pref_parser.read(pref, filename)
    except IOError, e:
        raise NoteBookError("Cannot read notebook preferences", e)
    except xmlo.XmlError, e:
        raise NoteBookError("Notebook preference data is corrupt", e)

    return pref.version
    

#=============================================================================
# classes

class NoteBookError (StandardError):
    """Exception that occurs when manipulating NoteBook's"""
    
    def __init__(self, msg, error=None):
        StandardError.__init__(self)
        self.msg = msg
        self.error = error
    
    
    def __str__(self):
        if self.error is not None:
            return repr(self.error) + "\n" + self.msg
        else:
            return self.msg


class NoteBookVersionError (NoteBookError):
    """Exception for version errors while reading notebooks"""

    def __init__(self, notebook_version, readable_version,  error=None):
        NoteBookError.__init__(self,
            "Notebook version '%d' is higher than what is readable '%d'" %
                               (notebook_version,
                                readable_version),
                               error)
        self.notebook_version = notebook_version
        self.readable_version = readable_version

# TODO: finish

class NoteBookAttr (object):

    def __init__(self, name, datatype, key=None, write=None, read=None):
        if key == None:
            self.key = name
        else:
            self.key = key
        self.name = name
        self.datatype = datatype

        
        # writer function
        if write is None:
            if datatype == bool:
                self.write = lambda x: unicode(int(x))
            else:
                self.write = unicode
        else:
            self.write = write

        # reader function
        if read is None:
            if datatype == bool:
                self.read = lambda x: bool(int(x))
            else:
                self.read = datatype
        else:
            self.read = read
        

class NoteBookTable (object):
    def __init__(self, name):
        self.name = name
        self.cols = []

        # TODO: add col widths
        # NoteBooks have tables and attrs

g_default_attrs = [
    NoteBookAttr("Title", unicode, "title"),
    NoteBookAttr("Content type", unicode, "content_type"),
    NoteBookAttr("Order", int, "order"),
    NoteBookAttr("Created", int, "created_time"),
    NoteBookAttr("Modified", int, "modified_time"),
    NoteBookAttr("Expaned", bool, "expanded"),
    NoteBookAttr("Expanded2", bool, "expanded2"),
    NoteBookAttr("Folder Sort", int, "info_sort"),
    NoteBookAttr("Folder Sort Direction", int, "info_sort_dir")
]


# TODO: parent might be an implict attr


# 1. attrs should be data that is optional (although keepnote has a few
# required entries).
# 2. attrs can appear in listview




class NoteBookNode (object):
    """A general base class for all nodes in a NoteBook"""

    def __init__(self, path, title="", parent=None, notebook=None,
                 content_type=CONTENT_TYPE_DIR):
        self._notebook = notebook
        self._parent = parent
        self._basename = None
        self._children = None        
        self._valid = True
        self._version = NOTEBOOK_FORMAT_VERSION
        self._meta = NoteBookNodeMetaData()
        
        self.clear_attr(title=title, content_type=content_type)

        # TODO: add a mechanism to register implict attrs that in turn do lookup
        # "parent", "nchildren"
        
        self._set_basename(path)
        
        

    def create(self):
        """Initializes the node on disk (create required files/directories)"""
        path = self.get_path()
        
        try:
            os.mkdir(path)
        except OSError, e:
            raise NoteBookError("Cannot create node", e)
            
        self._attr["created_time"] = get_timestamp()
        self._attr["modified_time"] = get_timestamp()
        self.write_meta_data()
        self._set_dirty(False)

        # TODO: move to NoteBookPage
        if self._attr["content_type"] == CONTENT_TYPE_PAGE:
            self.write_empty_data_file()



    def get_path(self):
        """Returns the directory path of the node"""
        
        path_list = []
        ptr = self
        while ptr is not None:
            path_list.append(ptr._basename)
            ptr = ptr._parent
        path_list.reverse()
        
        return os.path.join(* path_list)
            
    
    def _set_basename(self, path):
        """Sets the basename directory of the node"""
        if self._parent is None:
            self._basename = path
        elif path is None:
            self._basename = None
        else:
            self._basename = os.path.basename(path)


    def get_version(self):
        """Returns the format version of this node"""
        return self._version
    
    
    def get_title(self):
        """Returns the display title of a node"""
        if self._attr["title"] is None:
            self.read_meta_data()
        return self._attr["title"]
    
    
    def get_parent(self):
        """Returns the parent of the node"""
        return self._parent

    def get_notebook(self):
        """Returns the notebook that owns this node"""
        return self._notebook

    def get_order(self):
        #assert self._parent is not None
        #assert self._parent.get_children().index(self) == self._order
        return self._attr["order"]
    
    def is_valid(self):
        """Returns True if node is valid (not deleted)"""
        return self._valid
    
    def is_page(self):
        """Returns True if node is a page"""
        return self._attr["content_type"] == CONTENT_TYPE_PAGE


    def clear_attr(self, title="", content_type=CONTENT_TYPE_DIR):
        """Clear attributes (set them to defaults)"""
        
        self._attr = {
            "title": title,
            "content_type": content_type,
            "order": sys.maxint,
            "created_time": None,
            "modified_time": None,
            "expanded": False,
            "expanded2": False,
            "info_sort": INFO_SORT_NONE,
            "info_sort_dir": 1}
        
    
    def get_attr(self, name, default=None):
        """Get the value of an attribute"""
        return self._attr.get(name, default)

    def set_attr(self, name, value):
        """Set the value of an attribute"""
        self._attr[name] = value
        self._set_dirty(True)


    def del_attr(self, name):
        """Delete an attribute"""

        # TODO: check against un-deletable attributes
        
        del self._attr[name]
        

    def iter_attr(self):
        """Iterate through attributes"""
        return self._attr.iteritems()
    

    def set_attr_timestamp(self, name, timestamp=None):
        """Set a timestamp attribute"""
        if timestamp is None:
            timestamp = get_timestamp()
        self._attr[name] = timestamp
        self._set_dirty(True)
            

    def set_info_sort(self, info, sort_dir):
        """Sets the sorting information of the node"""
        self._attr["info_sort"] = info
        self._attr["info_sort_dir"] = sort_dir
        self._set_dirty(True)
    
    def get_info_sort(self):
        """Gets the sorting information of the node"""
        return (self._attr["info_sort"], self._attr["info_sort_dir"])

    def _set_dirty(self, dirty):
        """Sets the dirty bit to indicates whether node needs saving"""
        self._notebook._set_dirty_node(self, dirty)
        
    def _is_dirty(self):
        """Returns True if node needs saving"""
        return self._notebook._is_dirty_node(self)

    
    def move(self, parent, index=None):
        """Move this node to be the child of another node 'parent'"""
        
        assert self != parent
        path = self.get_path()
        old_parent = self._parent
        
        # perform on-disk move if new parent
        if old_parent != parent:
            path2 = os.path.join(parent.get_path(), self._basename)
            parent_path = os.path.dirname(path2)
            path2 = get_valid_unique_filename(parent_path, self._attr["title"])
            
            try:
                os.rename(path, path2)
            except OSError, e:
                raise NoteBookError("Do not have permission for move", e)
        
            self._set_basename(path2)

        # perform move in data structure
        self._parent._remove_child(self)
        if self._parent != parent:
            self._parent._set_child_order()
            self._parent = parent
            self._parent._add_child(self, index)
        else:
            if self._attr["order"] < index:
                index -= 1
            self._parent._add_child(self, index)
        self._set_dirty(True)
        self.save(True)

        # notify listeners
        if parent != old_parent:
            self.notify_changes([old_parent, parent], True)
        else:
            old_parent.notify_change(True)

        
    
    def delete(self):
        """Deletes this node from the notebook"""

        path = self.get_path()
        try:      
            shutil.rmtree(path)
        except OSError, e:
            raise NoteBookError("Do not have permission to delete", e)
        
        self._parent._remove_child(self)
        self._parent._set_child_order()
        self._valid = False
        self._set_dirty(False)
        
        # make sure to recursively invalidate
        def walk(node):
            """Uncache children list"""

            if node._children is not None:
                for child in node._children:
                    child._valid = False
                    walk(child)
        walk(self)

        # parent node notifies listeners of change
        self._parent.notify_change(True)
    
    
    def trash(self):
        """Places node in the notebook's trash folder"""

        if self._notebook is None:
            raise NoteBookError("This node is not part of any notebook")
        
        if self.in_trash():
            # delete if in trash folder already
            self.delete()
            
        else:
            # move to trash            
            self.move(self._notebook._trash)
        
        
    
    def in_trash(self):
        """Determines if node is inside Trash folder"""
        
        ptr = self._parent
        while ptr is not None:
            if ptr == self._notebook._trash:
                return True
            ptr = ptr._parent
        return False
    
    
    def rename(self, title):
        """Renames the title of the node"""
        
        # do noting if title is the same
        if title == self._attr["title"]:
            return
        
        if self._parent is None:
            # don't rename the directory of the notebook itself
            # just change the title
            self._attr["title"] = title
            self._set_dirty(True)
            return
        
        # try to pick a path that closely resembles the title
        path = self.get_path()
        parent_path = os.path.dirname(path)
        path2 = get_valid_unique_filename(parent_path, title)

        try:
            os.rename(path, path2)
            self._attr["title"] = title
            self._set_basename(path2)
            self.save(True)
        except (OSError, NoteBookError), e:
            raise NoteBookError("Cannot rename '%s' to '%s'" % (path, path2), e)
        
        self.notify_change(False)


    # TODO: refactor this to a kind argument and make a factory function...
    
    def new_page(self, title=DEFAULT_PAGE_NAME):
        """Add a new page under node"""
        path = self.get_path()
        newpath = get_valid_unique_filename(path, title)
        page = NoteBookPage(newpath, title=title, parent=self,
                            notebook=self._notebook)
        page.create()
        self._add_child(page)
        page.save(True)
        self.notify_change(True)
        return page
    
    
    def new_dir(self, title=DEFAULT_DIR_NAME):
        """Add a new folder under node"""
        path = self.get_path()
        newpath = get_valid_unique_filename(path, title)
        node = NoteBookDir(newpath, title=title, parent=self,
                           notebook=self._notebook)
        node.create()
        self._add_child(node)
        node.save(True)
        self.notify_change(True)
        return node
    
    
    def get_children(self):
        """Returns all children of this node"""
        if self._children is None:
            self._get_children()
        
        return self._children
    
    
    def _get_children(self):
        """Load children list from filesystem"""
        self._children = []
        path = self.get_path()
        
        try:
            files = os.listdir(path)
        except OSError, e:
            raise NoteBookError("Do not have permission to read folder contents", e)
        
        for filename in files:
            path2 = os.path.join(path, filename)
            
            try:
                node = self._notebook.read_node(self, path2)
                if node:
                    self._children.append(node)
                
            except NoteBookError, e:
                continue                
                # TODO: raise warning, not all children read
                            
        
        # assign orders
        self._children.sort(key=lambda x: x._attr["order"])
        self._set_child_order()

    
    def _set_child_order(self):
        """Ensures that child know their order in the children list"""
        for i, child in enumerate(self._children):
            if child._attr["order"] != i:
                child._attr["order"] = i
                child._set_dirty(True)
            

    def _add_child(self, child, index=None):
        """Add a node as a child"""
        
        # propogate notebook
        child._notebook = self._notebook
        
        if self._children is None:
            self._get_children()
        
        if index is not None:
            # insert child at index
            self._children.insert(index, child)
            self._set_child_order()
        elif self._notebook and \
             len(self._children) > 0 and \
             self._children[-1] == self._notebook.get_trash():
            # append child before trash
            self._children.insert(len(self._children)-1, child)
            self._set_child_order()
        else:
            # append child at end of list
            child._attr["order"] = len(self._children)
            self._children.append(child)

        child._set_dirty(True)
    

    def _remove_child(self, child):
        """Remove a child node"""
        if self._children is None:
            self._get_children()
        self._children.remove(child)


    #===============================================
    # listeners
    
    def notify_change(self, recurse):
        """Notify listeners that node has changed"""
        if self._notebook:
            self._notebook.node_changed.notify([self], recurse)

    def notify_changes(self, nodes, recurse):
        """Notify listeners that several nodes have changed"""
        if self._notebook:
            self._notebook.node_changed.notify(nodes, recurse)
    
    def suppress_change(self, listener=None):
        """Suppress notification of listeners for node changes"""
        if self._notebook:
            self._notebook.node_changed.suppress(listener)

    def resume_change(self, listener=None):
        """Resume notification of listeners for node changes"""        
        if self._notebook:
            self._notebook.node_changed.resume(listener)


    #==============================================
    # input/output
    
    def load(self):
        """Load a node from filesystem"""
        self.read_meta_data()
    
    
    def save(self, force=False):
        """Save node if modified (dirty)"""
        
        if (force or self._is_dirty()) and self._valid:
            self.write_meta_data()
            self._set_dirty(False)
            
    def get_data_file(self):
        """Returns filename of data/text/html/etc"""
        return get_page_data_file(self.get_path())


    def read_data_as_plain_text(self):
        """Iterates over the lines of the data file as plain text"""
        
        filename = self.get_data_file()
        infile = open(filename)

        for line in read_data_as_plain_text(infile):
            yield line
            
    
    def write_empty_data_file(self):
        """Initializes an empty data file on file-system"""
        datafile = self.get_data_file()
        
        try:
            out = safefile.open(datafile, "w", codec="utf-8")
            out.write(BLANK_NOTE)
            out.close()
        except IOError, e:
            raise NoteBookError("Cannot initialize richtext file '%s'" % datafile, e)
        
        
    def get_meta_file(self):
        """Returns the meta file for the node"""
        return get_node_meta_file(self.get_path())

    def write_meta_data(self):
        
        self._meta.write(self.get_meta_file(),
                         self,
                         self._notebook.notebook_attrs)

    def read_meta_data(self):
        self._meta.read(self.get_meta_file(),
                        self._notebook.notebook_attrs)
        self.set_meta_data(self._meta.attr)


    def set_meta_data(self, attr):
        self._version = self._meta.attr.get("version", NOTEBOOK_FORMAT_VERSION)
        self._attr.update(attr)
        

class NoteBookNodeMetaData (object):
    """Reads and writes metadata for NoteBookNode objects"""

    def __init__(self):
        self.attr = {}
        self._notebook_attrs = {}

        self._parser = None

        self.__meta_root = False
        self.__meta_data = None
        self.__meta_tag = None

                    
    def write(self, filename, node, notebook_attrs):
        
        try:
            out = safefile.open(filename, "w", codec="utf-8")
            out.write(XML_HEADER)
            out.write("<node>\n"
                      "<version>%s</version>\n" % node.get_version())
            
            for key, val in node.iter_attr():
                attr = notebook_attrs.get(key, None)
                
                if attr is not None:
                    out.write('<attr key="%s">%s</attr>\n' %
                              (key, escape(attr.write(val))))
                elif key == "version":
                    # skip version attr
                    pass
                elif isinstance(val, basestring):
                    # write unknown attrs
                    out.write('<attr key="%s">%s</attr>\n' %
                              (escape(key), escape(val)))
                else:
                    # drop attribute
                    pass

            out.write("</node>\n")
            out.close()
        except Exception, e:
            print e
            raise NoteBookError("Cannot write meta data", e)


    def read(self, filename, notebook_attrs):

        self._notebook_attrs = notebook_attrs
        self.attr = {}

        # prep attrs
        self.attr["created_time"] = None
        self.attr["modified_time"] = None    

    
        try:            
            self.__meta_root = False
            self.__meta_data = None
            self.__meta_tag = None

            self._parser = xml.parsers.expat.ParserCreate()
            self._parser.StartElementHandler = self.__meta_start_element
            self._parser.EndElementHandler = self.__meta_end_element
            self._parser.CharacterDataHandler = self.__meta_char_data

            infile = open(filename, "rb")
            self._parser.ParseFile(infile)
            infile.close()
            
        except xml.parsers.expat.ExpatError, e:
            raise NoteBookError("Cannot read meta data", e)
        
        except Exception, e:
            raise NoteBookError("Cannot read meta data", e)

        # set defaults
        if self.attr["created_time"] is None:
            self.attr["created_time"] = get_timestamp()
            #set_dirty(True)
        if self.attr["modified_time"] is None:
            self.attr["modified_time"] = get_timestamp()
            #self._set_dirty(True)


    def __meta_start_element(self, name, attrs):

        # NOTE: assumes no nested tags

        if self.__meta_root:
            if self.__meta_tag is not None:
                raise Exception("corrupt meta file")
                
            self.__meta_tag = name
            self.__meta_attr = attrs
            self.__meta_data = ""

        elif name == "node":
            self.__meta_root = True
        
        
    def __meta_end_element(self, name):

        if name == "node":
            self.__meta_root = False

        if not self.__meta_root:
            return
        
        if self.__meta_tag == "version":
            self.attr["version"] = int(self.__meta_data)

        elif self.__meta_tag == "attr":
            key = self.__meta_attr.get("key", None)
            if key is not None:
                attr = self._notebook_attrs.get(key, None)
                if attr is not None:
                    self.attr[key] = attr.read(self.__meta_data)
                else:
                    # unknown attribute is read as a string
                    self.attr[key] = self.__meta_data

        # clear state
        self.__meta_tag = None
        self.__meta_attr = None
        self.__meta_data = None
                
        
    def __meta_char_data(self, data):
        """read character data and give it to current tag"""

        if self.__meta_data is not None:
            self.__meta_data += data
            


class NoteBookPage (NoteBookNode):
    """Class that represents a Page in the NoteBook"""
    
    def __init__(self, path, title="", parent=None, notebook=None):
        NoteBookNode.__init__(self, path, title, parent, notebook,
                              content_type=CONTENT_TYPE_PAGE)


class NoteBookDir (NoteBookNode):
    """Class that represents Folders in NoteBook"""
    
    def __init__(self, path, title="", parent=None, notebook=None):
        NoteBookNode.__init__(self, path, title, parent, notebook,
                              content_type=CONTENT_TYPE_DIR)



class NoteBookTrash (NoteBookDir):
    """Class represents the Trash Folder in a NoteBook"""

    def __init__(self, name, notebook):
        NoteBookDir.__init__(self, get_trash_dir(notebook.get_path()), 
                             name, parent=notebook, notebook=notebook)
        self.set_attr("content_type", CONTENT_TYPE_TRASH)
        
        
    def move(self, parent, index=None):
        """Trash folder only be under root directory"""
        
        if parent == self._notebook:
            assert parent == self._parent
            NoteBookDir.move(self, parent, index)
        else:
            raise NoteBookError("The Trash folder must be a top-level folder.")
    
    def delete(self):
        """Trash folder cannot be deleted"""
        
        raise NoteBookError("The Trash folder cannot be deleted.")


class NoteBookPreferences (object):
    """Preference data structure for a NoteBook"""
    def __init__(self):
        
        self.version = NOTEBOOK_FORMAT_VERSION
        self.default_font = DEFAULT_FONT



# file format for NoteBook preferences
g_notebook_pref_parser = xmlo.XmlObject(
    xmlo.Tag("notebook", tags=[
        xmlo.Tag("version",
            getobj=("version", int),
            set=lambda s: str(s.version)),
        xmlo.Tag("default_font",
            getobj=("default_font", str),
            set=lambda s: s.default_font),
        ]))
    

class NoteBook (NoteBookDir):
    """Class represents a NoteBook"""
    
    def __init__(self, rootdir=None):
        """rootdir -- Root directory of notebook"""
        NoteBookDir.__init__(self, rootdir, notebook=self)
        self.pref = NoteBookPreferences()
        if rootdir is not None:
            self._attr["title"] = os.path.basename(rootdir)
        else:
            self._attr["title"] = None
        self._dirty = set()
        self._trash = None
        
        self._attr["order"] = 0

        # init notebook attributes
        self.notebook_attrs = {}
        for attr in g_default_attrs:
            self.notebook_attrs[attr.key] = attr
        
        if rootdir:
            self._trash_path = get_trash_dir(self.get_path())
        
        # listeners
        self.node_changed = Listeners()  # node, recurse

        # add node types
        self._node_factory = NoteBookNodeFactory()
        self._node_factory.add_node_type(
            CONTENT_TYPE_DIR,
            lambda path, parent, notebook, attr:
            NoteBookDir(path,
                        parent=parent,
                        notebook=notebook))
        self._node_factory.add_node_type(
            CONTENT_TYPE_PAGE,
            lambda path, parent, notebook, attr:
            NoteBookPage(path,
                         parent=parent,
                         notebook=notebook))
        self._node_factory.add_node_type(
            CONTENT_TYPE_TRASH,
            lambda path, parent, notebook, attr:
            NoteBookTrash(TRASH_NAME, notebook))


    def get_trash(self):
        """Returns the Trash Folder for the NoteBook"""
        return self._trash        

    def _set_dirty_node(self, node, dirty):
        """Mark a node to be dirty (needs saving) in NoteBook"""
        if dirty:
            self._dirty.add(node)
        else:
            if node in self._dirty:
                self._dirty.remove(node)
    
    
    def _is_dirty_node(self, node):
        """Returns True if node is dirty (needs saving)"""
        return node in self._dirty
        
    
    def save_needed(self):
        """Returns True if save is needed"""
        return len(self._dirty) > 0
        
        
    def create(self):
        """Initialize NoteBook on the file-system"""
        
        NoteBookDir.create(self)
        os.mkdir(self.get_pref_dir())
        self.write_meta_data()
        self.write_preferences()

    
    def get_root_node(self):
        """Returns the root node of the notebook"""
        return self
    
    
    def load(self, filename=None):
        """Load the NoteBook from the file-system"""
        if filename is not None:
            if os.path.isdir(filename):
                self._set_basename(filename)
            elif os.path.isfile(filename):
                filename = os.path.dirname(filename)
                self._set_basename(filename)
            else:
                raise NoteBookError("Cannot find notebook '%s'" % filename)
            
            self._trash_path = get_trash_dir(self.get_path())
        self.read_meta_data()
        self.read_preferences()
        self.notify_change(True)
    
    
    def save(self, force=False):
        """Recursively save any loaded nodes"""

        if force or self in self._dirty:
            self.write_meta_data()
            self.write_preferences()
        
        self._set_dirty(False)

        if force:
            for node in self.get_children():
                node.save(force=force)
        else:
            for node in list(self._dirty):
                node.save()
        
        self._dirty.clear()
        

    def read_node(self, parent, path):
        return self._node_factory.read_node(self, parent, path)
        
    
    def get_children(self):
        """Returns all children of this node"""
        if self._children is None:
            self._get_children()        
            self._init_trash()
        
        return self._children


    def _init_trash(self):
        # ensure trash directory exists
        self._trash = None
        for child in self._children:
            if self.is_trash_dir(child):
                self._trash = child
                break

        # if no trash folder, create it
        if self._trash is None:
            try:
                self._trash = NoteBookTrash(TRASH_NAME, self)
                self._trash.create()
                self._add_child(self._trash)
            except NoteBookError, e:
                raise NoteBookError("Cannot create Trash folder", e)


    
    
    def is_trash_dir(self, child):
        """Returns True if child node is the Trash Folder"""
        return child.get_path() == self._trash_path


    def empty_trash(self):
        """Deletes all nodes under Trash Folder"""

        if self._trash is None:
            self._init_trash()

        for child in reversed(list(self._trash.get_children())):
            child.delete()
        
        
    
    #===============================================
    # preferences
    
    def get_pref_file(self):
        """Gets the NoteBook's preference file"""
        return get_pref_file(self.get_path())
    
    def get_pref_dir(self):
        """Gets the NoteBook's preference directory"""
        return get_pref_dir(self.get_path())
    
    
    def write_preferences(self):
        """Writes the NoteBooks preferences to the file-system"""
        try:
            # ensure preference directory exists
            if not os.path.exists(self.get_pref_dir()):
                os.mkdir(self.get_pref_dir())

            g_notebook_pref_parser.write(self.pref, self.get_pref_file())
        except (IOError, OSError), e:
            raise NoteBookError("Cannot save notebook preferences", e)
        except xmlo.XmlError, e:
            raise NoteBookError("File format error", e)

    
    def read_preferences(self):
        """Reads the NoteBook's preferneces from the file-system"""
        try:
            g_notebook_pref_parser.read(self.pref, self.get_pref_file())
        except IOError, e:
            raise NoteBookError("Cannot read notebook preferences", e)
        except xmlo.XmlError, e:
            raise NoteBookError("Notebook preference data is corrupt", e)

        
        if self.pref.version > NOTEBOOK_FORMAT_VERSION:
            raise NoteBookVersionError(self.pref.version,
                                       NOTEBOOK_FORMAT_VERSION)



class NoteBookNodeFactory (object):

    def __init__(self):
        self._makers = {}


    def add_node_type(self, content_type, make_func):
        self._makers[content_type] = make_func
        
    
    def read_node(self, notebook, parent, path):
        filename = os.path.basename(path)
        metafile = get_node_meta_file(path)        
        meta = NoteBookNodeMetaData()
        node = None

        if os.path.exists(metafile):
            meta.read(metafile, notebook.notebook_attrs)
            
            maker = self._makers.get(meta.attr.get("content_type",
                                                   CONTENT_TYPE_DIR), None)
            if maker:
                node = maker(path, parent, notebook, meta.attr)
                node.set_meta_data(meta.attr)                
            else:
                # ignore unknown node
                # TODO: could add some error handling error
                # or add NoteBookUnknownNode()
                pass
        else:
            # ignore directory, not a NoteBook directory            
            pass

        return node

