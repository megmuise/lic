from PyQt4.QtGui import QUndoCommand
from PyQt4.QtCore import SIGNAL, QSizeF

import Helpers

def resetGLItem(self, name, template):
    instructions = template.getPage().instructions

    if name == "CSI":
        template.resetPixmap()
        template.getPage().initLayout()
        for s, l in instructions.initCSIDimensions(0, True):
            pass  # Don't care about yielded items here

    elif name == "PLI":
        template.resetPixmap()
        template.getPage().initLayout()
        for s, l in instructions.initPartDimensions(0, True):
            pass  # Don't care about yielded items here
        instructions.initAllPLILayouts()

    elif name == "Submodel":
        template.resetPixmap()
        template.getPage().initLayout()
        instructions.initSubmodelImages()

NextCommandID = 122
def getNewCommandID():
    global NextCommandID
    NextCommandID += 1
    return NextCommandID

QUndoCommand.id = lambda self: self._id
QUndoCommand.undo = lambda self: self.doAction(False)
QUndoCommand.redo = lambda self: self.doAction(True)
QUndoCommand.resetGLItem = resetGLItem

class MoveCommand(QUndoCommand):

    """
    MoveCommand stores a list of parts moved together:
    itemList[0] = (item, item.oldPos, item.newPos)
    """

    _id = getNewCommandID()
    
    def __init__(self, itemList):
        QUndoCommand.__init__(self, "move Page Object")

        self.itemList = []
        for item in itemList:
            self.itemList.append((item, item.oldPos, item.pos()))

    def undo(self):
        for item, oldPos, newPos in self.itemList:
            item.setPos(oldPos)
            if hasattr(item.parentItem(), "resetRect"):
                item.parentItem().resetRect()

    def redo(self):
        for item, oldPos, newPos in self.itemList:
            item.setPos(newPos)
            if hasattr(item.parentItem(), "resetRect"):
                item.parentItem().resetRect()

class CalloutArrowMoveCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, part, oldPoint, newPoint):
        QUndoCommand.__init__(self, "move Callout Arrow")
        self.part, self.oldPoint, self.newPoint = part, oldPoint, newPoint

    # Need to invalidate scene because we don't actually move a part here, so scene doesn't redraw
    def undo(self):
        self.part.point = self.oldPoint
        self.part.scene().invalidate(self.part.parentItem().boundingRect())

    def redo(self):
        self.part.point = self.newPoint
        self.part.scene().invalidate(self.part.parentItem().boundingRect())

class DisplacePartCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, part, oldDisp, newDisp):
        QUndoCommand.__init__(self, "Part displacement")
        self.part, self.oldDisp, self.newDisp = part, oldDisp, newDisp

    def undo(self):
        self.part.displacement = list(self.oldDisp)
        self.part.getCSI().resetPixmap()

    def redo(self):
        self.part.displacement = list(self.newDisp)
        self.part.getCSI().resetPixmap()

class BeginEndDisplacementCommand(QUndoCommand):
    
    _id = getNewCommandID()

    def __init__(self, part, direction, end = False):
        if end:
            QUndoCommand.__init__(self, "Remove Part displacement")
            self.undo, self.redo = self.redo, self.undo
        else:
            QUndoCommand.__init__(self, "Begin Part displacement")
        self.part, self.direction = part, direction

    def undo(self):
        part = self.part
        part.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
        part.removeDisplacement()
        part.scene().emit(SIGNAL("layoutChanged()"))
        part.getCSI().resetPixmap()

    def redo(self):
        part = self.part
        part.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
        part.addNewDisplacement(self.direction)
        part.scene().emit(SIGNAL("layoutChanged()"))
        part.getCSI().resetPixmap()

class ResizePageCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, licWindow, oldPageSize, newPageSize, oldResolution, newResolution, doRescale):
        QUndoCommand.__init__(self, "Page Resize")
        
        self.licWindow = licWindow
        self.oldPageSize, self.newPageSize = oldPageSize, newPageSize
        self.oldResolution, self.newResolution = oldResolution, newResolution
        self.doRescale = doRescale
        self.oldScale = 1.0
        self.newScale = float(newPageSize.width()) / float(oldPageSize.width())

        if doRescale:  # Temp error check
            os, ns = QSizeF(oldPageSize), QSizeF(newPageSize)
            if (os.width() / os.height()) != (ns.width() / ns.height()):
                print "Cannot rescale page items with new aspect ratio"
            if (ns.width() / os.width()) != (ns.height() / os.height()):
                print "Cannot rescale page items with uneven width / height scales"
        
    def undo(self):
        self.licWindow.setPageSize(self.oldPageSize, self.oldResolution, self.doRescale, self.oldScale)
    
    def redo(self):
        self.licWindow.setPageSize(self.newPageSize, self.newResolution, self.doRescale, self.newScale)
    
class MoveStepToPageCommand(QUndoCommand):

    """
    stepSet stores a list of (step, oldPage, newPage) tuples:
    stepSet = [(step1, oldPage1, newPage1), (step2, oldPage2, newPage2)]
    """

    _id = getNewCommandID()

    def __init__(self, stepSet):
        QUndoCommand.__init__(self, "move Step to Page")
        self.stepSet = stepSet

    def undo(self):
        for step, oldPage, newPage in self.stepSet:
            step.moveToPage(oldPage)
            oldPage.initLayout()
            newPage.initLayout()

    def redo(self):
        for step, oldPage, newPage in self.stepSet:
            step.moveToPage(newPage)
            newPage.initLayout()
            oldPage.initLayout()

class SwapStepsCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, step1, step2):
        QUndoCommand.__init__(self, "Swap Steps")
        self.step1, self.step2 = step1, step2
        
    def doAction(self, redo):
        s1, s2 = self.step1, self.step2
        p1, p2 = s1.parentItem(), s2.parentItem()
        
        p1.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
        i1, i2 = s1.row(), s2.row()
        p1.children[i1], p2.children[i2] = p2.children[i2], p1.children[i1]
        
        i1, i2 = p1.steps.index(s1), p2.steps.index(s2)
        p1.steps[i1], p2.steps[i2] = p2.steps[i2], p1.steps[i1]
        
        s1.number, s2.number = s2.number, s1.number
        s1.setParentItem(p2)
        s2.setParentItem(p1)
        
        p1.initLayout()
        p2.initLayout()
        p1.scene().emit(SIGNAL("layoutAboutToBeChanged()"))

class AddRemoveStepCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, step, addStep):
        QUndoCommand.__init__(self, "%s Step" % ("add" if addStep else "delete"))
            
        self.step, self.addStep = step, addStep
        self.parent = step.parentItem()

    def doAction(self, redo):
        parent = self.parent
        if (redo and self.addStep) or (not redo and not self.addStep):
            parent.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
            parent.insertStep(self.step)
            parent.scene().emit(SIGNAL("layoutChanged()"))
            self.step.setSelected(True)
        else:
            self.step.setSelected(False)
            parent.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
            parent.removeStep(self.step)                
            parent.scene().emit(SIGNAL("layoutChanged()"))
        parent.initLayout()

class AddRemoveCalloutCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, callout, addCallout):
        QUndoCommand.__init__(self, "%s Callout" % ("add" if addCallout else "delete"))
            
        self.callout, self.addCallout = callout, addCallout
        self.parent = callout.parentItem()

    def doAction(self, redo):
        parent = self.parent
        if (redo and self.addCallout) or (not redo and not self.addCallout):
            parent.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
            parent.addCallout(self.callout)
            parent.scene().emit(SIGNAL("layoutChanged()"))
        else:
            self.callout.setSelected(False)
            parent.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
            parent.removeCallout(self.callout)                
            parent.scene().emit(SIGNAL("layoutChanged()"))
        parent.initLayout()

class AddRemovePageCommand(QUndoCommand):

    # TODO: Remove instructions.emit from here
    _id = getNewCommandID()

    def __init__(self, page, addPage):
        QUndoCommand.__init__(self, "%s Page" % ("add" if addPage else "delete"))
        self.page, self.addPage = page, addPage

    def doAction(self, redo):
        page = self.page
        page.instructions.emit(SIGNAL("layoutAboutToBeChanged()"))

        if (redo and self.addPage) or (not redo and not self.addPage):
            page.parent().addPage(page)
            number = page.number
        else:
            page.parent().deletePage(page)
            number = page.number - 1

        page.instructions.emit(SIGNAL("layoutChanged()"))
        page.instructions.scene.selectPage(number)

class AddRemoveGuideCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, scene, guide, addGude):
        QUndoCommand.__init__(self, "%s Guide" % ("add" if addGude else "remove"))
        self.scene, self.guide, self.addGude = scene, guide, addGude

    def doAction(self, redo):

        if (redo and self.addGude) or (not redo and not self.addGude):
            self.scene.guides.append(self.guide)
            self.scene.addItem(self.guide)
        else:
            self.scene.removeItem(self.guide)
            self.scene.guides.remove(self.guide)

class MovePartsToStepCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, partList, newStep):
        QUndoCommand.__init__(self, "move Part to Step")
        self.newStep = newStep
        self.partListStepPairs = [(p, p.getStep()) for p in partList]

    def doAction(self, redo):
        self.newStep.scene().clearSelection()
        self.newStep.scene().emit(SIGNAL("layoutAboutToBeChanged()"))

        redoSubmodelOrder = False
        stepsToReset = set([self.newStep])
        
        for part, oldStep in self.partListStepPairs:
            if part.filename == 'arrow':
                continue
            startStep = oldStep if redo else self.newStep
            endStep = self.newStep if redo else oldStep
            
            part.setParentItem(endStep) # Temporarily set part's parent, so it doesn't get deleted by Qt
            startStep.removePart(part)
            endStep.addPart(part)
            if part.displacement and part.displaceArrow:
                startStep.csi.removeArrow(part.displaceArrow)
                endStep.csi.addArrow(part.displaceArrow)
                
            if part.isSubmodel():
                redoSubmodelOrder = True
            stepsToReset.add(oldStep)

        if redoSubmodelOrder:
            mainModel = self.newStep.getPage().instructions.mainModel
            mainModel.reOrderSubmodelPages()
            mainModel.syncPageNumbers()
        
        self.newStep.scene().emit(SIGNAL("layoutChanged()"))

        # Need to refresh each step between the lowest and highest numbers
        minStep = min(stepsToReset, key = lambda step: step.number)
        maxStep = max(stepsToReset, key = lambda step: step.number)

        nextStep = minStep.getNextStep()
        while (nextStep is not None and nextStep.number < maxStep.number):
            stepsToReset.add(nextStep)
            nextStep = nextStep.getNextStep()
            
        for step in stepsToReset:
            step.csi.isDirty = True
            step.initLayout()
            if step.isInCallout():
                step.parentItem().initLayout()
    
class AddRemovePartsToCalloutCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, callout, partList, addParts):
        QUndoCommand.__init__(self, "%s Part to Callout" % ("add" if addParts else "remove"))
        self.callout, self.partList, self.addParts = callout, partList, addParts

    def doAction(self, redo):
        self.callout.scene().emit(SIGNAL("layoutAboutToBeChanged()"))

        for part in self.partList:
            if (redo and self.addParts) or (not redo and not self.addParts):
                self.callout.addPart(part)
            else:
                self.callout.removePart(part)

        self.callout.scene().emit(SIGNAL("layoutChanged()"))
        self.callout.steps[-1].csi.resetPixmap()
        self.callout.initLayout()

class ToggleStepNumbersCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, callout, enableNumbers):
        QUndoCommand.__init__(self, "%s Step Numbers" % ("show" if enableNumbers else "hide"))
        self.callout, self.enableNumbers = callout, enableNumbers

    def doAction(self, redo):
        self.callout.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
        if (redo and self.enableNumbers) or (not redo and not self.enableNumbers):
            self.callout.enableStepNumbers()
        else:
            self.callout.disableStepNumbers()
        self.callout.scene().emit(SIGNAL("layoutChanged()"))
        self.callout.initLayout()

class ToggleCalloutQtyCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, callout, enableQty):
        QUndoCommand.__init__(self, "%s Callout Quantity" % ("Add" if enableQty else "Remove"))
        self.callout, self.enableQty = callout, enableQty

    def doAction(self, redo):
        self.callout.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
        if (redo and self.enableQty) or (not redo and not self.enableQty):
            self.callout.addQuantityLabel()
        else:
            self.callout.removeQuantityLabel()
        self.callout.scene().emit(SIGNAL("layoutChanged()"))
        self.callout.initLayout()

class ChangeCalloutQtyCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, callout, qty):
        QUndoCommand.__init__(self, "Change Callout Quantity")
        self.callout, self.qty = callout, qty
        self.oldQty = self.callout.getQuantity()

    def doAction(self, redo):
        self.callout.setQuantity(self.qty if redo else self.oldQty)
                
class AdjustArrowLength(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, arrow, oldLength, newLength):
        QUndoCommand.__init__(self, "change arrow length")
        self.arrow, self.oldLength, self.newLength = arrow, oldLength, newLength

    def doAction(self, redo):
        length = self.newLength if redo else self.oldLength
        self.arrow.setLength(length)
        self.arrow.getCSI().resetPixmap()

class AdjustArrowRotation(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, arrow, oldRotation, newRotation):
        QUndoCommand.__init__(self, "change arrow rotation")
        self.arrow, self.oldRotation, self.newRotation = arrow, oldRotation, newRotation

    def doAction(self, redo):
        self.arrow.axisRotation = self.newRotation if redo else self.oldRotation
        self.arrow.getCSI().resetPixmap()
        
class ScaleItemCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, target, oldScale, newScale):
        QUndoCommand.__init__(self, "Item Scale")
        self.target, self.oldScale, self.newScale = target, oldScale, newScale

    def doAction(self, redo):
        self.target.scaling = self.newScale if redo else self.oldScale
        self.target.resetPixmap() 
        self.target.getPage().initLayout()
    
class RotateItemCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, target, oldRotation, newRotation):
        QUndoCommand.__init__(self, "Item rotation")
        self.target, self.oldRotation, self.newRotation = target, oldRotation, newRotation

    def doAction(self, redo):
        self.target.rotation = list(self.newRotation) if redo else list(self.oldRotation)
        self.target.resetPixmap() 
        self.target.getPage().initLayout()

class ScaleDefaultItemCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, target, name, template, oldScale, newScale):
        QUndoCommand.__init__(self, "Change default %s Scale" % name)
        self.target, self.name, self.template = target, name, template
        self.oldScale, self.newScale = oldScale, newScale

    def doAction(self, redo):
        self.target.defaultScale = self.newScale if redo else self.oldScale
        self.resetGLItem(self.name, self.template)
        self.template.scene().update()  # Need this to force full redraw
            
class RotateDefaultItemCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, target, name, template, oldRotation, newRotation):
        QUndoCommand.__init__(self, "Change default %s rotation" % name)
        self.target, self.name, self.template = target, name, template
        self.oldRotation, self.newRotation = oldRotation, newRotation

    def doAction(self, redo):
        self.target.defaultRotation = list(self.newRotation) if redo else list(self.oldRotation)
        self.resetGLItem(self.name, self.template)
        
class SetPageBackgroundColorCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, template, oldColor, newColor):
        QUndoCommand.__init__(self, "change Page background")
        self.template, self.oldColor, self.newColor = template, oldColor, newColor

    def doAction(self, redo):
        color = self.newColor if redo else self.oldColor
        self.template.setColor(color)
        self.template.update()
        for page in self.template.instructions.getPageList():
            page.color = color
            page.update()

class SetPageBackgroundBrushCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, template, oldBrush, newBrush):
        QUndoCommand.__init__(self, "change Page background")
        self.template, self.oldBrush, self.newBrush = template, oldBrush, newBrush

    def doAction(self, redo):
        brush = self.newBrush if redo else self.oldBrush
        self.template.setBrush(brush)
        self.template.update()
        for page in self.template.instructions.getPageList():
            page.brush = brush
            page.update()

class SetPenCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, target, oldPen, newPen):
        QUndoCommand.__init__(self, "change Border")
        self.target, self.oldPen, self.newPen = target, oldPen, newPen
        self.template = target.getPage()

    def doAction(self, redo):
        pen = self.newPen if redo else self.oldPen
        self.target.setPen(pen)
        self.target.update()
        for page in self.template.instructions.getPageList():
            for child in page.getAllChildItems():
                if self.target.itemClassName == child.itemClassName:
                    child.setPen(pen)
                    child.update()

class SetBrushCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, target, oldBrush, newBrush):
        QUndoCommand.__init__(self, "change Border")
        self.target, self.oldBrush, self.newBrush = target, oldBrush, newBrush
        self.template = target.getPage()

    def doAction(self, redo):
        brush = self.newBrush if redo else self.oldBrush
        self.target.setBrush(brush)
        self.target.update()
        for page in self.template.instructions.getPageList():
            for child in page.getAllChildItems():
                if self.target.itemClassName == child.itemClassName:
                    child.setBrush(brush)
                    child.update()
    
class SetItemFontsCommand(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, template, oldFont, newFont, target):
        QUndoCommand.__init__(self, "change " + target + " font")
        self.template, self.oldFont, self.newFont, self.target = template, oldFont, newFont, target

    def doAction(self, redo):
        font = self.newFont if redo else self.oldFont
        if self.target == 'Page':
            self.template.numberItem.setFont(font)
            for page in self.template.instructions.getPageList():
                page.numberItem.setFont(font)
                
        elif self.target == 'Step':
            self.template.steps[0].numberItem.setFont(font)
            for page in self.template.instructions.getPageList():
                for step in page.steps:
                    step.numberItem.setFont(font)
                    
        elif self.target == 'PLI Item':
            for item in self.template.steps[0].pli.pliItems:
                item.numberItem.setFont(font)
            for page in self.template.instructions.getPageList():
                for step in page.steps:
                    for item in step.pli.pliItems:
                        item.numberItem.setFont(font)

class TogglePLIs(QUndoCommand):

    _id = getNewCommandID()

    def __init__(self, template, enablePLIs):
        QUndoCommand.__init__(self, "%s PLIs" % ("Enable" if enablePLIs else "Remove"))
        self.template, self.enablePLIs = template, enablePLIs

    def doAction(self, redo):
        self.template.scene().emit(SIGNAL("layoutAboutToBeChanged()"))
        if (redo and self.enablePLIs) or (not redo and not self.enablePLIs):
            self.template.enablePLI()
        else:
            self.template.disablePLI()
        self.template.scene().emit(SIGNAL("layoutChanged()"))
        self.template.initLayout()
                
class ChangePartColorCommand(QUndoCommand):
    
    _id = getNewCommandID()
    
    def __init__(self, part, oldColor, newColor):
        QUndoCommand.__init__(self, "Change Part color")
        self.part, self.oldColor, self.newColor = part, oldColor, newColor

    def doAction(self, redo):
        oldColor, newColor = (self.oldColor, self.newColor) if redo else (self.newColor, self.oldColor)
        self.part.changeColor(newColor)
        if self.part.getStep().pli:
            self.part.getStep().pli.changePartColor(self.part, oldColor, newColor)

class SubmodelToCalloutCommand(QUndoCommand):
    
    _id = getNewCommandID()
    
    def __init__(self, submodel):
        QUndoCommand.__init__(self, "Submodel To Callout")
        self.submodel = submodel
        self.parentModel = submodel._parent
        
    def redo(self):
        # Convert a Submodel into a Callout

        self.targetStep = self.parentModel.findSubmodelStep(self.submodel)
        scene = self.targetStep.scene()
        scene.clearSelection()
        scene.emit(SIGNAL("layoutAboutToBeChanged()"))
        
        self.targetCallout = self.targetStep.addBlankCalloutSignal(False, False)

        # Find each instance of this submodel on the target page
        self.submodelInstanceList = []
        self.addedParts = []
        for part in self.targetStep.csi.getPartList():
            if part.partOGL == self.submodel:
                self.targetStep.removePart(part)
                self.submodelInstanceList.append(part)

        calloutDone = False
        for submodelPart in self.submodelInstanceList:
            for page in self.submodel.pages:
                for step in page.steps:
                    for part in step.csi.getPartList():
                        newPart = part.duplicate()
                        newPart.matrix = Helpers.multiplyMatrices(newPart.matrix, submodelPart.matrix)
                        self.addedParts.append(newPart)
                        
                        self.targetStep.addPart(newPart)
                        if not calloutDone:
                            self.targetCallout.addPart(newPart.duplicate())

                    if step != page.steps[-1] and not calloutDone:
                        self.targetCallout.addBlankStep(False)
                            
            calloutDone = True
        
        if len(self.submodelInstanceList) > 1:
            self.targetCallout.setQuantity(len(self.submodelInstanceList))
            
        for step in self.targetCallout.steps:
            step.csi.resetPixmap()
        self.targetStep.initLayout()
        self.targetCallout.initLayout()
                    
        self.parentModel.removeSubmodel(self.submodel)
        scene.emit(SIGNAL("layoutChanged()"))
        scene.selectPage(self.targetStep.parentItem().number)
        self.targetCallout.setSelected(True)
        scene.emit(SIGNAL("sceneClick"))
        
    def undo(self):
        # Convert a Callout into a Submodel
        # For now, assume this really is an undo, and we have a fully defined self.submodel, targetStep and targetCallout 
        
        scene = self.targetStep.scene()
        scene.clearSelection()
        scene.emit(SIGNAL("layoutAboutToBeChanged()"))
        
        for part in self.addedParts:
            self.targetStep.removePart(part)

        for submodel in self.submodelInstanceList:
            self.targetStep.addPart(submodel)

        self.parentModel.addSubmodel(self.submodel)
        
        self.targetStep.removeCallout(self.targetCallout)
        self.targetStep.initLayout()
        scene.emit(SIGNAL("layoutChanged()"))

        scene.selectPage(self.submodel.pages[0].number)
        self.submodel.pages[0].setSelected(True)
        scene.emit(SIGNAL("sceneClick"))

class CalloutToSubmodelCommand(SubmodelToCalloutCommand):

    _id = getNewCommandID()
    
    def __init__(self, callout):
        QUndoCommand.__init__(self, "Callout To Submodel")
        self.targetCallout = targetCallout
        
    def redo(self):
        self.targetStep = self.targetCallout.parentItem()
        
        self.addedParts = []
    
    def undo(self):
        pass

class SubmodelToFromSubAssembly(QUndoCommand):
    
    _id = getNewCommandID()
    
    def __init__(self, submodel, submodelToAssembly):
        text = "Submodel to Sub Assembly" if submodelToAssembly else "Sub Assembly to Submodel"
        QUndoCommand.__init__(self, text)
        self.submodel, self.submodelToAssembly = submodel, submodelToAssembly
    
    def doAction(self, redo):
        
        self.submodel.isSubAssembly = not self.submodel.isSubAssembly
        do = (redo and self.submodelToAssembly) or (not redo and not self.submodelToAssembly)
        self.submodel.showHidePLIs(not do)
        submodelItem = self.submodel.pages[0].submodelItem
        submodelItem.convertToSubAssembly() if do else submodelItem.convertToSubmodel()
