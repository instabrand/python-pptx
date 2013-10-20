# -*- coding: utf-8 -*-
#
# shapes.py
#
# Copyright (C) 2012, 2013 Steve Canny scanny@cisco.com
#
# This module is part of python-pptx and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""
Classes that implement PowerPoint shapes such as picture, textbox, and table.
"""

from pptx.autoshape import _AutoShapeType, _Shape
from pptx.constants import MSO
from pptx.oxml import qn, CT_GraphicalObjectFrame, CT_Picture, CT_Shape
from pptx.placeholder import _Placeholder
from pptx.shape import _BaseShape
from pptx.spec import namespaces, slide_ph_basenames
from pptx.spec import PH_ORIENT_VERT, PH_TYPE_DT, PH_TYPE_FTR, PH_TYPE_SLDNUM
from pptx.table import _Table
from pptx.util import Collection

# default namespace map for use in lxml calls
_nsmap = namespaces('a', 'r', 'p')


# ============================================================================
# Shapes
# ============================================================================

class _ShapeCollection(_BaseShape, Collection):
    """
    Sequence of shapes. Corresponds to CT_GroupShape in pml schema. Note that
    while spTree in a slide is a group shape, the group shape is recursive in
    that a group shape can include other group shapes within it.
    """
    _NVGRPSPPR = qn('p:nvGrpSpPr')
    _GRPSPPR = qn('p:grpSpPr')
    _SP = qn('p:sp')
    _GRPSP = qn('p:grpSp')
    _GRAPHICFRAME = qn('p:graphicFrame')
    _CXNSP = qn('p:cxnSp')
    _PIC = qn('p:pic')
    _CONTENTPART = qn('p:contentPart')
    _EXTLST = qn('p:extLst')

    def __init__(self, spTree, slide=None):
        super(_ShapeCollection, self).__init__(spTree)
        self.__spTree = spTree
        self.__slide = slide
        self.__shapes = self._values
        # unmarshal shapes
        for elm in spTree.iterchildren():
            if elm.tag in (self._NVGRPSPPR, self._GRPSPPR, self._EXTLST):
                continue
            elif elm.tag == self._SP:
                shape = _Shape(elm)
            elif elm.tag == self._PIC:
                shape = _Picture(elm)
            elif elm.tag == self._GRPSP:
                shape = _ShapeCollection(elm)
            elif elm.tag == self._GRAPHICFRAME:
                if elm.has_table:
                    shape = _Table(elm)
                else:
                    shape = _BaseShape(elm)
            elif elm.tag == self._CONTENTPART:
                msg = ("first time 'contentPart' shape encountered in the "
                       "wild, please let developer know and send example")
                raise ValueError(msg)
            else:
                shape = _BaseShape(elm)
            self.__shapes.append(shape)

    @property
    def placeholders(self):
        """
        Immutable sequence containing the placeholder shapes in this shape
        collection, sorted in *idx* order.
        """
        placeholders =\
            [_Placeholder(sp) for sp in self.__shapes if sp.is_placeholder]
        placeholders.sort(key=lambda ph: ph.idx)
        return tuple(placeholders)

    @property
    def title(self):
        """The title shape in collection or None if no title placeholder."""
        for shape in self.__shapes:
            if shape._is_title:
                return shape
        return None

    def add_picture(self, file, left, top, width=None, height=None):
        """
        Add picture shape displaying image in *file*, where *file* can be
        either a path to a file (a string) or a file-like object.
        """
        image, rel = self.__slide._add_image(file)

        id = self.__next_shape_id
        name = 'Picture %d' % (id-1)
        desc = image._desc
        rId = rel._rId
        width, height = image._scale(width, height)

        pic = CT_Picture.new_pic(id, name, desc, rId, left, top, width, height)

        self.__spTree.append(pic)
        picture = _Picture(pic)
        self.__shapes.append(picture)
        return picture

    def add_shape(self, autoshape_type_id, left, top, width, height):
        """
        Add auto shape of type specified by *autoshape_type_id* (like
        ``MSO.SHAPE_RECTANGLE``) and of specified size at specified position.
        """
        autoshape_type = _AutoShapeType(autoshape_type_id)
        id_ = self.__next_shape_id
        name = '%s %d' % (autoshape_type.basename, id_-1)

        sp = CT_Shape.new_autoshape_sp(id_, name, autoshape_type.prst,
                                       left, top, width, height)
        shape = _Shape(sp)

        self.__spTree.append(sp)
        self.__shapes.append(shape)
        return shape

    def add_table(self, rows, cols, left, top, width, height):
        """
        Add table shape with the specified number of *rows* and *cols* at the
        specified position with the specified size. *width* is evenly
        distributed between the *cols* columns of the new table. Likewise,
        *height* is evenly distributed between the *rows* rows created.
        """
        id = self.__next_shape_id
        name = 'Table %d' % (id-1)
        graphicFrame = CT_GraphicalObjectFrame.new_table(
            id, name, rows, cols, left, top, width, height)
        self.__spTree.append(graphicFrame)
        table = _Table(graphicFrame)
        self.__shapes.append(table)
        return table

    def add_textbox(self, left, top, width, height):
        """
        Add text box shape of specified size at specified position.
        """
        id_ = self.__next_shape_id
        name = 'TextBox %d' % (id_-1)

        sp = CT_Shape.new_textbox_sp(id_, name, left, top, width, height)
        shape = _Shape(sp)

        self.__spTree.append(sp)
        self.__shapes.append(shape)
        return shape

    def _clone_layout_placeholders(self, slidelayout):
        """
        Add placeholder shapes based on those in *slidelayout*. Z-order of
        placeholders is preserved. Latent placeholders (date, slide number,
        and footer) are not cloned.
        """
        latent_ph_types = (PH_TYPE_DT, PH_TYPE_SLDNUM, PH_TYPE_FTR)
        for sp in slidelayout.shapes:
            if not sp.is_placeholder:
                continue
            ph = _Placeholder(sp)
            if ph.type in latent_ph_types:
                continue
            self.__clone_layout_placeholder(ph)

    def __clone_layout_placeholder(self, layout_ph):
        """
        Add a new placeholder shape based on the slide layout placeholder
        *layout_ph*.
        """
        id_ = self.__next_shape_id
        ph_type = layout_ph.type
        orient = layout_ph.orient
        shapename = self.__next_ph_name(ph_type, id_, orient)
        sz = layout_ph.sz
        idx = layout_ph.idx

        sp = CT_Shape.new_placeholder_sp(id_, shapename, ph_type, orient,
                                         sz, idx)
        shape = _Shape(sp)

        self.__spTree.append(sp)
        self.__shapes.append(shape)
        return shape

    def __next_ph_name(self, ph_type, id, orient):
        """
        Next unique placeholder name for placeholder shape of type *ph_type*,
        with id number *id* and orientation *orient*. Usually will be standard
        placeholder root name suffixed with id-1, e.g.
        __next_ph_name(PH_TYPE_TBL, 4, 'horz') ==> 'Table Placeholder 3'. The
        number is incremented as necessary to make the name unique within the
        collection. If *orient* is ``'vert'``, the placeholder name is
        prefixed with ``'Vertical '``.
        """
        basename = slide_ph_basenames[ph_type]
        # prefix rootname with 'Vertical ' if orient is 'vert'
        if orient == PH_ORIENT_VERT:
            basename = 'Vertical %s' % basename
        # increment numpart as necessary to make name unique
        numpart = id - 1
        names = self.__spTree.xpath('//p:cNvPr/@name', namespaces=_nsmap)
        while True:
            name = '%s %d' % (basename, numpart)
            if name not in names:
                break
            numpart += 1
        return name

    @property
    def __next_shape_id(self):
        """
        Next available drawing object id number in collection, starting from 1
        and making use of any gaps in numbering. In practice, the minimum id
        is 2 because the spTree element is always assigned id="1".
        """
        cNvPrs = self.__spTree.xpath('//p:cNvPr', namespaces=_nsmap)
        ids = [int(cNvPr.get('id')) for cNvPr in cNvPrs]
        ids.sort()
        # first gap in sequence wins, or falls off the end as max(ids)+1
        next_id = 1
        for id in ids:
            if id > next_id:
                break
            next_id += 1
        return next_id


class _Picture(_BaseShape):
    """
    A picture shape, one that places an image on a slide. Corresponds to the
    ``<p:pic>`` element.
    """
    def __init__(self, pic):
        super(_Picture, self).__init__(pic)

    @property
    def shape_type(self):
        """
        Unique integer identifying the type of this shape, unconditionally
        ``MSO.PICTURE`` in this case.
        """
        return MSO.PICTURE
