import math   # for sqrt
import cairo  # for gui preview drawing
import os     # for output path creation

import GLHelpers

from LDrawColors import *
from LDrawFileFormat import *
from Drawables import *

from OpenGL.GL import *
from OpenGL.GLU import *

# TODO: Each class holds a bunch of self attributes only used during initialization - once init is done, delete them maybe?
# TODO: File load is sluggish, even if loading from a thoroughly Lic-created file - speed it up

# Globals
UNINIT_OGL_DISPID = -1
partDictionary = {}   # x = PartOGL("3005.dat"); partDictionary[x.filename] == x
_docWidth = 800
_docHeight = 600

# TODO: Save the default image size to the file if its not there already
class Instructions:
	"""	Represents an overall Lego instruction booklet.	"""
	
	# TODO: Instructions should be a tree, and be used more cleanly than the hack job currently in the tree GUI code.
	def __init__(self, filename):
		
		# Part dimensions cache line format: filename width height center.x center.y leftInset bottomInset
		self.ImgDimensionsFilename = "PartDimensions_" + filename + ".cache"
		self.filename = filename
		
		self.mainModel = Part(filename, isMainModel = True)
	
	def getMainModel(self):
		return self.mainModel
	
	def getCurrentModel(self):
		pass

	def generateImages(self):
		global _docWidth, _docHeight
		
		print "*** Generating Instructions ***"
		rawFilename = os.path.splitext(os.path.basename(self.mainModel.partOGL.filename))[0]
		path = os.path.join(os.getcwd(), rawFilename + '_images')
		if not os.path.isdir(path):
			os.mkdir(path)
		
		surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, _docWidth, _docHeight)
		context = cairo.Context(surface)
		
		for page in self.mainModel.partOGL.pages:
			page.drawToFile(surface, context, path)
		
		print "*** Generate Instructions Complete ***"
	
	def initDraw(self, context):
		
		# Calculate the width and height of each partOGL in the part dictionary and each CSI
		self.initPartDimensions()
		self.initCSIDimensions()
		
		# Calculate an initial layout for each Step and PLI in this instruction book
		for page in self.mainModel.partOGL.pages:
			for step in page.steps:
				step.initLayout(context)
				step.writeToFileArray(self.mainModel.partOGL.ldrawFile)

	def initPartDimensions(self):
		
		try:
			# Have a valid part dimension cache file for this model - load from there
			f = file(self.ImgDimensionsFilename, "r")
			self.initPartDimensionsFromFile(f)
			f.close()
		except IOError:
			# Need to calculate all part dimensions from scratch
			self.initPartDimensionsManually()

	def initPartDimensionsFromFile(self, f):
		""" Used to initialize all part dimensions from the specified valid part dimension cache file f."""
		
		# TODO: If there's a part in the model but not in this file, need to
		# generate a size for it manually, then append that entry to the file
		# TODO: Make the part cache file not model specific, but rendered dimensions specific
		for line in f:
			filename, w, h, x, y, l, b = line.split()
			if not partDictionary.has_key(filename):
				print "Warning: part dimension cache contains part (%s) not present in model - suggest regenerating part dimension cache." % (filename)
				continue
			p = partDictionary[filename]
			p.width = max(1, int(w))
			p.height = max(1, int(h))
			p.center = Point(int(x), int(y))
			p.leftInset = int(l)
			p.bottomInset = int(b)
	
	def buildCSIList(self, part, loadedParts = []):
		csiList = []
		for page in part.pages:
			for step in page.steps:
				for part in step.parts:
					if part.partOGL.filename not in loadedParts and part.partOGL.pages != []:
						csiList += self.buildCSIList(part.partOGL, loadedParts)
					loadedParts.append(part.partOGL.filename)
				if step.csi.fileLine is None:
					csiList.append(step.csi)
		return csiList

	def initCSIDimensions(self):
		
		csiList = self.buildCSIList(self.mainModel.partOGL)
		if csiList == []:
			return  # All CSIs initialized - nothing to do here
		
		csiList2 = []
		sizes = [512, 1024, 2048] # Frame buffer sizes to try - could make configurable by user, if they've got lots of big submodels
		
		for size in sizes:
			
			# Create a new FBO
			buffers = GLHelpers.createFBO(size, size)
			if buffers is None:
				print "ERROR: Failed to initialize FBO - aborting initCSIDimensions"
				return
			
			# Render each CSI and calculate its size
			for csi in csiList:
				if not csi.initSize(size):
					csiList2.append(csi)
			
			# Clean up created FBO
			GLHelpers.destroyFBO(*buffers)
			
			if len(csiList2) < 1:
				break  # All images initialized successfully
			else:
				csiList = csiList2  # Some images rendered out of frame - loop and try bigger frame
				csiList2 = []
	
	def initPartDimensionsManually(self):
		"""
		Used to calculate each part's display width and height if no valid part dimension cache file exists.
		Creates GL FBOs to render a temp copy of each part, then uses those raw pixels to determine size.
		Will create and store results in a part dimension cache file.
		"""
		
		partList = [part for part in partDictionary.values() if not part.isPrimitive]
		partList2 = []
		lines = []
		sizes = [128, 256, 512, 1024, 2048] # Frame buffer sizes to try - could make configurable by user, if they've got lots of big submodels
		
		for size in sizes:
			
			# Create a new FBO
			buffers = GLHelpers.createFBO(size, size)
			if buffers is None:
				print "ERROR: Failed to initialize FBO - aborting initPartDimensionsManually"
				return
			
			# Render each image and calculate their sizes
			for partOGL in partList:
				
				if partOGL.initSize(size):  # Draw image and calculate its size:					
					lines.append(partOGL.dimensionsToString())
				else:
					partList2.append(partOGL)
			
			# Clean up created FBO
			GLHelpers.destroyFBO(*buffers)
			
			if len(partList2) < 1:
				break  # All images initialized successfully
			else:
				partList = partList2  # Some images rendered out of frame - loop and try bigger frame
				partList2 = []
		
		# Create an image dimension cache file
		print ""
		f = open(self.ImgDimensionsFilename, "w")
		f.writelines(lines)
		f.close()
	
class Page:
	"""
	A single page in an instruction book.
	"""
	
	def __init__(self, number):
		
		self.box = Box()
		self.fill = Fill()
		
		self.number = number
		self.steps = []
		self.fileLine = None
		
		self.numberLabel = Label(str(self.number))
		self.pagePadding = 20

	def initPageSize(self, width, height, context = None):
		global _docWidth, _docHeight
		
		# Save the specified page size to this page's box
		self.box.x = max(self.pagePadding, (width - _docWidth) / 2.0)
		self.box.y = max(self.pagePadding, (height - _docHeight) / 2.0)
		self.box.width = _docWidth
		self.box.height = _docHeight
		
		# Position page label in bottom right corner of page
		# TODO: Page number is moveable, but position is not saved to file - update LIC PAGE command to include page number position & font
		if context and self.numberLabel.refPt is None:
			self.numberLabel.setBottomRightCorner(_docWidth - self.pagePadding, _docHeight - self.pagePadding, context)
	
	def drawPage(self, context):
		
		# Flood context with grey background
		context.set_source_rgb(0.5, 0.5, 0.5)
		context.paint()
		
		# Draw a slightly down-left translated black rectangle, for the page shadow effect
		context.translate(self.box.x, self.box.y)
		context.set_source_rgb(0,0,0)
		context.rectangle(1, 1, self.box.width + 3, self.box.height + 3)
		context.fill()
		
		# Draw the page itself - white with a thin black border
		context.rectangle(0, 0, self.box.width, self.box.height)
		context.stroke_preserve()
		context.set_source_rgb(1,1,1)
		context.fill()
	
	def draw(self, context, width, height, selection = None):
		
		# Let this Page know how big it should be drawn
		self.initPageSize(width, height, context)
		
		# Draw the overall page frame
		# drawPage leaves the cairo context translated to the top left corner of the page but *NOT* scaled - scaling here messes up GL drawing
		self.drawPage(context)
		self.numberLabel.draw(context)
		
		# Fully reset the viewport - necessary if we've mangled it while calculating part dimensions
		GLHelpers.adjustGLViewport(0, 0, width, height)
		GLHelpers.glLoadIdentity()	
		GLHelpers.rotateToDefaultView()
		
		# Draw each step in this page
		for step in self.steps:
			step.draw()
		
		# Copy GL buffer to a new cairo surface, then dump that surface to the current context
		pixels = glReadPixels (0, 0, width, height, GL_RGBA,  GL_UNSIGNED_BYTE)
		surface = cairo.ImageSurface.create_for_data(pixels, cairo.FORMAT_ARGB32, width, height, width * 4)
		context.set_source_surface(surface)
		context.paint()
		surface.finish()
		
		# Draw any remaining 2D page elements, like borders, labels, etc
		for step in self.steps:
			step.drawPageElements(context)
		
		if selection:
			box = selection.boundingBox()
			if box:
				box.growBy(2)
				box.drawAsSelection(context)
	
	def drawToFile(self, surface, context, path):
		
		pngFile = os.path.join(path, "page_%d.png" % (self.number))
		if not os.path.isfile(pngFile):
			context.set_source_rgb(1, 1, 1)
			context.paint()
			
			for step in self.steps:
				step.drawToFile(surface, context)
			
			print "Generating page %d" % (self.number)
			self.numberLabel.draw(context)
			surface.write_to_png(pngFile)
		
		for step in self.steps:
			step.drawSubModelsToFile(surface, context)
	
	def boundingBox(self):
		return None
	
	def select(self, x, y):
		# Translate passed in point by the amount this page is displaced from top left corner
		x -= self.box.x
		y -= self.box.y
		if self.numberLabel.boundingBox().ptInBox(x, y):
			return self.numberLabel
		for step in self.steps:
			if step.boundingBox().ptInBox(x, y):
				return step.select(x, y)
		return None  # If we're here, nothing clicked on

class BOM:
	"""
	Bill Of Materials - just an elaborate PLI, containing a list of all parts in the model, nicely laid out.
	"""
	pass

class Callout:
	def __init__(self):
		self.box = Box(0, 0)

# TODO: Fix PLI and PLIItem by moving all quantity label stuff out of PLI into PLIItem, then replace it with Label
class PLIItem:
	def __init__(self, partOGL, count, corner, labelCorner, xBearing, partLine):
		self.partOGL = partOGL
		self.count = count
		self.corner = corner
		self.labelCorner = labelCorner
		self.xBearing = xBearing
		self.partLine = partLine
		self.fileLine = None

	def writeToFileArray(self, ldrawFile, filename, color):
		line = [Comment, LicCommand, PLIItemCommand, filename, self.count, self.corner.x, self.corner.y, self.labelCorner.x, self.labelCorner.y, self.xBearing, color]
		self.fileLine = ldrawFile.insertLine(self.partLine[0], line)
	
	def draw(self, color):
		p = self.partOGL
		GLHelpers.adjustGLViewport(self.corner.x, self.corner.y - p.height, p.width, p.height)
		glLoadIdentity()
		GLHelpers.rotateToPLIView(p.center.x, p.center.y, 0.0)
		glColor3fv(convertToRGBA(color))
		p.draw()
	
	def drawToFile(self, context, color):
		p = self.partOGL
		p.renderToPov(color)
		imageSurface = cairo.ImageSurface.create_from_png(self.partOGL.pngFile)
		context.set_source_surface(imageSurface, round(self.corner.x), round(self.corner.y - p.height))
		context.paint()

	def boundingBox(self):
		p = self.partOGL
		b = Box(self.corner.x, self.corner.y - p.height, p.width, p.height)
		b.growByXY(self.labelCorner.x - self.xBearing, self.labelCorner.y)
		return b
	
	def moveBy(self, x, y):
		self.corner.moveBy(x, y)
		self.labelCorner.moveBy(x, y)
		self.updateFileLine()

	def updateFileLine(self):
		self.fileLine[6] = str(self.corner.x)
		self.fileLine[7] = str(self.corner.y)
		self.fileLine[8] = str(self.labelCorner.x)
		self.fileLine[9] = str(self.labelCorner.y)

class PLI:
	"""
	Parts List Image.  Includes border and layout info for a list of parts added to a step.
	"""
	
	def __init__(self, step, topLeftCorner = Point(10, 10)):
		
		self.box = Box(topLeftCorner.x, topLeftCorner.y)
		self.qtyLabelFont = Font(size = 14, bold = True)
		self.qtyMultiplierChar = 'x'
		self.layout = {}  # {(part filename, color): PLIItem instance}
		
		self.step = step
		self.fileLine = None

	def isEmpty(self):
		if len(self.layout) > 0:
			return False
		return True

	def addPart(self, part):
		
		item = (part.partOGL.filename, part.color)
		
		if item in self.layout:
			self.layout[item].count += 1
			self.layout[item].partLine = part.fileLine
		else:  # TODO: think about including filename / color in item.  It'd mean redundant info, but easier iteration (over values instead of items) and fewer method args
			self.layout[item] = PLIItem(part.partOGL, 1, Point(), Point(), 0, part.fileLine)  # TODO: check PLIItem default arg constructor
	
	def initLayout(self, context):
		
		# If this PLI is empty, nothing to do here
		if len(self.layout) < 1:
			return
		
		# Return the height of the part in the specified layout item
		def itemHeight(layoutItem):
			return layoutItem.partOGL.height
		
		# Compare the width of layout Items 1 and 2
		def compareLayoutItemWidths(item1, item2):
			""" Returns 1 if part 2 is wider than part 1, 0 if equal, -1 if narrower. """
			if item1.partOGL.width < item2.partOGL.width:
				return 1
			if item1.partOGL.width == item2.partOGL.width:
				return 0
			return -1
		
		# Sort the list of parts in this PLI from widest to narrowest, with the tallest one first
		partList = self.layout.values()
		tallestPart = max(partList, key=itemHeight)
		partList.remove(tallestPart)
		partList.sort(compareLayoutItemWidths)
		partList.insert(0, tallestPart)
		
		# Note that PLI box's top left corner must be set by container before this layout call
		b = self.box
		overallX = b.x + b.internalGap
		b.width = b.height = -1
		
		#for i, (corner, labelCorner) in enumerate(partList):
		for i, item in enumerate(partList):
			
			# Calculate and store this part's bottom left corner
			item.corner.x = overallX
			item.corner.y = b.y + b.internalGap + item.partOGL.height
			
			# Check if the current PLI box is big enough to fit this part *below* the previous part,
			# without making the box any bigger.  If so, position part there instead.
			newWidth = item.partOGL.width
			if i > 0:
				prevCorner = partList[i-1].corner
				prevLabelCorner = partList[i-1].labelCorner
				remainingHeight = b.y + b.height - b.internalGap - b.internalGap - prevCorner.y
				if item.partOGL.height < remainingHeight:
					if prevCorner.x > prevLabelCorner.x:
						overallX = int(prevLabelCorner.x)
						newWidth = (prevCorner.x - overallX) + partList[i-1].partOGL.width
					else:
						overallX = prevCorner.x
						newWidth = partList[i-1].partOGL.width
					item.corner.x = overallX + (newWidth - item.partOGL.width)
					item.corner.y = prevCorner.y + b.internalGap + item.partOGL.height
			
			# Position the part quantity label
			item.labelCorner.x, item.labelCorner.y, xBearing, xHeight = self.initQtyLabelPos(context, item.count, item.partOGL, item.corner)
			
			if item.labelCorner.x < overallX:
				# We're trying to draw the label to the left of the part's current position - shift everything
				dx = overallX - item.labelCorner.x
				overallX += dx
				item.labelCorner.x += dx
				item.corner.x += dx
			
			# Account for any x bearing in label (space between left corner of bounding box and actual reference point)
			item.xBearing = xBearing
			item.labelCorner.x -= xBearing
			
			# Increase overall x, box width and box height to make PLI box big enough for this part
			overallX += newWidth + b.internalGap
			b.width = overallX - b.x
			b.height = max(b.height, item.partOGL.height + int(xHeight / 2) + (b.internalGap * 2))

	def initQtyLabelPos(self, context, count, part, partCorner):
		
		# Tell cairo to use the quantity label's current font
		self.qtyLabelFont.passToCairo(context)
		
		# Figure out the display height of multiplier label and the width of full quantity label
		label = str(count) + self.qtyMultiplierChar
		xbearing, ybearing,     xWidth,     xHeight, xa, ya = context.text_extents(self.qtyMultiplierChar)
		xbearing, ybearing, labelWidth, labelHeight, xa, ya = context.text_extents(label)
		
		# Position label based on part corner, empty corner triangle and label's size
		if part.leftInset == part.bottomInset == 0:
			dx = -3   # Bottom left triangle is empty - shift just a little, for a touch more padding
		else:
			slope = part.leftInset / float(part.bottomInset)
			dx = ((part.leftInset - (xHeight / 2)) / slope) - 3  # 3 for a touch more padding
		
		x = int(partCorner.x - labelWidth + max(0, dx))
		y = int(partCorner.y + (xHeight / 2))
		return (x, y, xbearing, xHeight)
	
	def drawParts(self):
		""" Must be called inside a valid gldrawable context. """
		
		if len(self.layout) < 1:
			return  # No parts in this PLI - nothing to draw
		
		GLHelpers.pushAllGLMatrices()
		glPushAttrib(GL_CURRENT_BIT)
		
		for (filename, color), item in self.layout.items():
			item.draw(color)
		
		glPopAttrib()
		GLHelpers.popAllGLMatrices()

	def drawToFile(self, context):
		
		if len(self.layout) < 1:
			return  # No parts in this PLI - nothing to draw
		
		for (filename, color), item in self.layout.items():
			item.drawToFile(context, color)

	def drawPageElements(self, context):
		""" Draw this PLI's background, border and quantity labels to the specified cairo context. """
		
		if len(self.layout) < 1:
			return  # No parts in this PLI - nothing to draw
		
		# Draw the PLIs overall bounding box
		self.box.draw(context)
		
		# Draw the quantity label for each part, if needed
		for item in self.layout.values():
			self.qtyLabelFont.passToCairo(context)
			context.move_to(item.labelCorner.x, item.labelCorner.y)
			context.show_text(str(item.count) + self.qtyMultiplierChar)

	def writeToFileArray(self, ldrawFile):
		
		if self.fileLine:
			return  # If this PLI already has a file line, it means it already exists in the file
		
		# Write out the main PLI command to file, including box and label position info
		line = [Comment, LicCommand, PLICommand,
				self.box.x, self.box.y, self.box.width, self.box.height,
				self.qtyMultiplierChar, self.qtyLabelFont.size, self.qtyLabelFont.face,
				self.step.numberLabel.refPt.x, self.step.numberLabel.refPt.y,
				self.step.numberLabel.font.size, self.step.numberLabel.font.face]
		self.fileLine = ldrawFile.insertLine(self.step.fileLine[0], line)
		
		# Write out each PLI item in the layout, positioned right after the last occurance of the part in this step
		for (filename, color), item in self.layout.items():
			item.writeToFileArray(ldrawFile, filename, color)

	def boundingBox(self):
		return Box(box = self.box)
		
	def select(self, x, y):
		if self.boundingBox().ptInBox(x, y):
			for item in self.layout.values():
				if item.boundingBox().ptInBox(x, y):
					return item
			return self
		return None
	
	def moveBy(self, x, y):
		self.box.moveBy(x, y)
		for item in self.layout.values():
			item.moveBy(x, y)
		self.updateFileLine()

	def updateFileLine(self):
		self.fileLine[4] = str(self.box.x)
		self.fileLine[5] = str(self.box.y)
		self.fileLine[6] = str(self.box.width)
		self.fileLine[7] = str(self.box.height)
		self.fileLine[8] = str(self.qtyMultiplierChar)
		self.fileLine[9] = str(self.qtyLabelFont.size)
		self.fileLine[10] = str(self.qtyLabelFont.face)
		self.fileLine[11] = str(self.step.numberLabel.refPt.x)
		self.fileLine[12] = str(self.step.numberLabel.refPt.y)
		self.fileLine[13] = str(self.step.numberLabel.font.size)
		self.fileLine[14] = str(self.step.numberLabel.font.face)

class CSI:
	"""
	Construction Step Image.  Includes border and positional info.
	"""
	
	def __init__(self, step, buffers):
		
		self.box = Box()
		self.center = Point()
		
		self.offsetPLI = 0
		self.step = step
		self.buffers = buffers  # [(bufID, stepNumber)], set of buffers active inside this CSI
		
		self.oglDispIDs = []  # [(dispID, buffer)]
		self.oglDispID = UNINIT_OGL_DISPID
		
		self.fileLine = None
	
	def initSize(self, size):
		"""
		Initialize this CSI's display width, height and center point. To do
		this, draw this CSI to the already initialized GL Frame Buffer Object.
		These dimensions are required to properly lay out PLIs and CSIs.
		Note that an appropriate FBO *must* be initialized before calling initSize.
		
		Parameters:
			size: Width & height of FBO to render to, in pixels.  Note that FBO is assumed square.
		
		Returns:
			True if CSI rendered successfully.
			False if the CSI has been rendered partially or wholly out of frame.
		"""
		
		# TODO: update some kind of load status bar her - this function is *slow*
		print "CSI %s step %d - size %d" % (self.step.filename, self.step.number, size)
		
		rawFilename = os.path.splitext(os.path.basename(self.step.filename))[0]
		filename = "%s_step_%d" % (rawFilename, self.step.number)
		
		params = GLHelpers.initImgSize(size, size, self.oglDispID, True, filename, self.step.rotStep)
		if params is None:
			return False
		
		self.box.width, self.box.height, self.center, x, y = params
		return True

	def callPreviousOGLDisplayLists(self, currentBuffers = None):
		if self.step.prevStep:
			self.step.prevStep.csi.callPreviousOGLDisplayLists(currentBuffers)
		
		if currentBuffers == []:
			# Draw the default list, since there's no buffers present
			glCallList(self.oglDispIDs[0][0])
		else:
			# Have current buffer - draw corresponding list (need to search for it)
			for id, buffer in self.oglDispIDs:
				if buffer == currentBuffers:
					glCallList(id)
					return
		
		# If we get here, no better display list was found, so call the default display list
		glCallList(self.oglDispIDs[0][0])

	def createOGLDisplayList(self):
		
		self.oglDispIDs = []
		self.oglDispID = -1
		
		# Ensure all parts in this step have proper display lists
		for part in self.step.parts:
			if part.partOGL.oglDispID == UNINIT_OGL_DISPID:
				part.partOGL.createOGLDisplayList()
		
		# Convert the list of buffers into a list of the concatenated buffer stack
		# TODO: Ugly - find a more pythonic way to do this
		bufferStackList = [[]]
		for buffer in self.buffers:
			tmp = list(bufferStackList[-1])
			tmp.append(buffer)
			bufferStackList.append(tmp)
		
		# Create one display list for each buffer set present in this Step
		for buffers in bufferStackList:
			id = glGenLists(1)
			self.oglDispIDs.append((id, buffers))
			glNewList(id, GL_COMPILE)
			
			for part in self.step.parts:
				part.callOGLDisplayList(buffers)
			
			glEndList()
		
		self.oglDispID = glGenLists(1)
		glNewList(self.oglDispID, GL_COMPILE)
		self.callPreviousOGLDisplayLists(self.buffers)
		glEndList()

	def draw(self):
		GLHelpers.adjustGLViewport(self.box.x, self.box.y, self.box.width, self.box.height)
		glLoadIdentity()
		GLHelpers.rotateToDefaultView(self.center.x, self.center.y, 0.0)
		if self.step.rotStep:
			GLHelpers.rotateViewByPoint3D(self.step.rotStep['point'])
		glCallList(self.oglDispID)

	def drawPageElements(self, context):
		self.box.draw(context)
		#pass

	def callOGLDisplayList(self):
		glCallList(self.oglDispIDs[0][0])
	
	def writeToFileArray(self, ldrawFile):
		
		line = [Comment, LicCommand, CSICommand,
						 self.box.x, self.box.y, self.box.width, self.box.height,
						 self.center.x, self.center.y]
		
		self.fileLine = ldrawFile.insertLine(self.step.fileLine[0], line)

	def renderToPov(self, ldrawFile, datFilename):
		camera = GLHelpers.getDefaultCamera()
		if self.step.rotStep:
			pt = self.step.rotStep['point']
			camera = [('z', pt.z), ('y', pt.y), ('x', pt.x)] + camera
		self.pngFile = ldrawFile.createPov(self.box.width, self.box.height, datFilename, camera, self.center)

	def drawToFile(self, context):
		imageSurface = cairo.ImageSurface.create_from_png(self.pngFile)
		context.set_source_surface(imageSurface, round(self.box.x), round(self.box.y))
		context.paint()

	def resize(self):
		global _docWidth, _docHeight
		self.box.x = (_docWidth / 2.) - (self.box.width / 2.)
		self.box.y = ((_docHeight - self.offsetPLI) / 2.) - (self.box.height / 2.) + self.offsetPLI
	
	def partTranslateCallback(self):
		global _docWidth, _docHeight
		self.createOGLDisplayList()
		self.initSize(min(_docWidth, _docHeight))
		self.resize()
	
	def boundingBox(self):
		return Box(box = self.box)
	
	def moveBy(self, x, y):
		self.box.moveBy(x, y)
		self.updateFileLine()

	def updateFileLine(self):
		self.fileLine[4] = str(self.box.x)
		self.fileLine[5] = str(self.box.y)

class Step:
	def __init__(self, filename, prevStep, buffers, containingPart):
		self.parts = []
		self.prevStep = prevStep
		self.containingPart = containingPart
		
		if prevStep:
			self.number = prevStep.number + 1
			self.rotStep  = prevStep.rotStep   # {'state': state, 'point': Point3D}
		else:
			self.number = 1
			self.rotStep = None
		
		self.numberLabel = Label(str(self.number))
		self.internalGap = 20
		
		self.filename = filename
		self.fileLine = None
		
		self.csi = CSI(self, list(buffers))
		self.pli = PLI(self, Point(self.internalGap, self.internalGap))

	def addPart(self, part):
		self.parts.append(part)
		part.translateCallback = self.csi.partTranslateCallback
		
		if not part.ignorePLIState:
			self.pli.addPart(part)
	
	def resize(self):
		
		# Notify this step's CSI about the new size
		self.csi.resize()
		
		# Notify any steps in any sub models about the resize too
		for part in self.parts:
			for page in part.partOGL.pages:
				for step in page.steps:
					step.resize()

	def initLayout(self, context):
		
		# Ensure all sub model PLIs and steps are also initialized
		for part in self.parts:
			for page in part.partOGL.pages:
				for step in page.steps:
					step.initLayout(context)
		
		# If this step's PLI has not been initialized by the LDraw file (first run?), choose a nice initial layout
		if self.pli.fileLine is None:
			self.pli.initLayout(context)
		
		# Determine space between top page edge and bottom of PLI, including gaps
		topGap = self.internalGap * 2 + self.pli.box.height
		if self.pli.isEmpty():
			topGap = self.internalGap
		
		# Tell this step's CSI about the PLI, so it can center itself vertically better
		if self.csi.fileLine is None:
			self.csi.offsetPLI = topGap
			self.csi.resize()
		
		# Determine a nice default position for the Step Number Label
		if self.numberLabel.refPt is None:
			self.numberLabel.setTopLeftCorner(self.internalGap, topGap, context)
	
	def writeToFileArray(self, ldrawFile):
		self.pli.writeToFileArray(ldrawFile)
		self.csi.writeToFileArray(ldrawFile)
		
		for part in self.parts:
			for page in part.partOGL.pages:
				for step in page.steps:
					step.writeToFileArray(ldrawFile)

	def draw(self):
		""" Draw this step's CSI and PLI parts (not GUI elements, just the 3D GL bits) """
		self.pli.drawParts()
		self.csi.draw()

	def drawPageElements(self, context):
		""" Draw this step's PLI and CSI page elements, and this step's number label. """
		self.pli.drawPageElements(context)
		self.csi.drawPageElements(context)
		
		# Draw this step's number label
		self.numberLabel.draw(context)
	
	def drawToFile(self, surface, context):
		
		self.renderToPov()
		self.pli.drawToFile(context)
		self.csi.drawToFile(context)
		self.drawPageElements(context)
	
	def drawSubModelsToFile(self, surface, context, path):
		
		for part in self.parts:
			for page in part.partOGL.pages:
				page.drawToFile(surface, context, path)

	def renderToPov(self):
		
		p = self.containingPart
		start, end = p.ldArrayStartEnd if p.ldArrayStartEnd else (0, -1)
		datFilename = p.ldrawFile.splitOneStepDat(self.fileLine, self.number, self.filename, start, end)
		self.csi.renderToPov(p.ldrawFile, datFilename)

	def boundingBox(self):
		return self.pli.box + self.csi.box + self.numberLabel.box
	
	def select(self, x, y):
		if self.boundingBox().ptInBox(x, y):
			if self.numberLabel.boundingBox().ptInBox(x, y):
				return self.numberLabel
			if self.csi.boundingBox().ptInBox(x, y):
				return self.csi
			if self.pli.boundingBox().ptInBox(x, y):
				return self.pli.select(x, y)
			return self
		return None
	
	def moveBy(self, x, y):
		self.pli.moveBy(x, y)
		self.csi.moveBy(x, y)
		self.numberLabel.moveBy(x, y)

class PartOGL:
	"""
	Represents one 'abstract' part.  Could be regular part, like 2x4 brick, could be a 
	simple primitive, like stud.dat, could be a full submodel with its own steps, buffers, etc.  
	Used inside 'concrete' Part below. One PartOGL instance will be shared across several 
	Part instances.  In other words, PartOGL represents everything that two 2x4 bricks have
	in common when present in a model.
	"""
	
	def __init__(self, filename, parentLDFile = None, isMainModel = False, pageNumber = None):
		
		self.name = self.filename = filename
		self.ldrawFile = None
		self.ldArrayStartEnd = None  # list [start, end]
		
		self.inverted = False  # TODO: Fix this! inverted = GL_CW
		self.invertNext = False
		self.parts = []
		self.primitives = []
		self.oglDispID = UNINIT_OGL_DISPID
		self.isPrimitive = False  # primitive here means any file in 'P'
		
		self.firstPageNumber = pageNumber
		self.currentStep = None
		self.currentPage = self.prevPage = None
		self.pages = []
		
		self.buffers = []  #[(bufID, stepNumber)]
		self.ignorePLIState = False
		
		self.width = self.height = 1
		self.leftInset = self.bottomInset = 0
		self.center = Point(0, 0)
		
		if (parentLDFile is not None) and (filename in parentLDFile.subModelArray):
			self._loadFromSubModelArray(parentLDFile)
		else:
			self._loadFromFile(isMainModel)
		
		# Check if the last step in model is empty - occurs often, since we've implicitly
		# created a step before adding any parts and many models end with a Step.
		# If removing an empty step leaves the last page empty, remove that too
		if (len(self.pages) > 0) and (len(self.pages[-1].steps) > 0) and (self.pages[-1].steps[-1].parts == []):
			self.pages[-1].steps.pop()
			if len(self.pages[-1].steps) == 0:
				self.pages.pop()
		
		self.createOGLDisplayList()
	
	def _loadFromSubModelArray(self, ldrawFile):
		
		self.ldrawFile = ldrawFile
		
		self.ldArrayStartEnd = ldrawFile.subModelArray[self.filename]
		start, end = self.ldArrayStartEnd
		subModelArray = ldrawFile.fileArray[start + 1 : end]
		
		for line in subModelArray:
			self._loadOneLDrawLineCommand(line)

	def _loadFromFile(self, isMainModel):
		
		self.ldrawFile = LDrawFile(self.filename)
		if isMainModel:
			self.ldrawFile.addInitialSteps()
			self.ldrawFile.addDefaultPages()
			self.ldrawFile.addLicHeader()
			self.ldArrayStartEnd = [0]
		
		self.isPrimitive = self.ldrawFile.isPrimitive
		self.name = self.ldrawFile.name
		
		# Loop over the specified LDraw file array, skipping the first line
		for line in self.ldrawFile.fileArray[1:]:
			
			# A FILE line means we're finished loading this model
			if isValidFileLine(line):
				if isMainModel:
					self.ldArrayStartEnd.append(line[0] - 1)
				return
			
			self._loadOneLDrawLineCommand(line)
		
		if self.ldArrayStartEnd == [0]:
			self.ldArrayStartEnd = None

	def _loadOneLDrawLineCommand(self, line):
		
		if isValidPageLine(line):
			self.addPage(line)
		
		elif isValidStepLine(line):
			self.addStep(line)
	
		elif isValidRotStepLine(line):
			self.addRotStep(line)

		elif isValidPartLine(line):
			self.addPart(lineToPart(line), line)
		
		elif isValidGhostLine(line):
			self.addPart(lineToGhostPart(line), line)
		
		elif isValidBufferLine(line):
			self.addBuffer(lineToBuffer(line))
		
		elif isValidTriangleLine(line):
			self.addPrimitive(lineToTriangle(line), GL_TRIANGLES)
		
		elif isValidQuadLine(line):
			self.addPrimitive(lineToQuad(line), GL_QUADS)
		
		elif isValidLPubLine(line):
			
			if isValidLPubPLILine(line):
				self.setPLIState(line)
			
			elif isValidLPubSizeLine(line):
				global _docWidth, _docHeight
				_docWidth, _docHeight = lineToLPubSize(line)
		
		elif isValidLicLine(line):
			
			if isValidCSILine(line):
				self.addCSI(line)
			
			elif isValidPLILine(line):
				self.addPLI(line)
			
			elif isValidPLIItemLine(line):
				self.addPLIItem(line)

	def addPLI(self, line):
		
		if not self.currentStep:
			print "PLI Error: Trying to create a PLI outside of a step.  Line %d" % (line[0])
			return
		
		d = lineToPLI(line)
		pli = self.currentStep.pli
		pli.fileLine = line
		pli.box = d['box']
		pli.qtyMultiplierChar = d['qtyLabel']
		pli.qtyLabelFont = d['qtyFont']
		pli.step.numberLabel.refPt = d['stepLabelPt']
		pli.step.numberLabel.font = d['stepLabelFont']
	
	def addPLIItem(self, line):
		
		if not self.currentStep:
			print "PLI Item Error: Trying to add an item to a PLI outside of a step.  Line %d" % (line[0])
			return
		
		if len(self.currentStep.parts) < 1:
			print "PLI Item Error: Trying to add an item to a PLI inside a step with no parts.  Line %d" % (line[0])
			return
		
		d = lineToPLIItem(line)
		if not partDictionary.has_key(d['filename']):
			print "PLI item Error: Trying to add a non-existent part (%s) to a PLI.  Line %d" % (d['filename'], line[0])
			return
		
		partLine = self.currentStep.parts[-1].fileLine
		item = PLIItem(partDictionary[d['filename']], d['count'], d['corner'], d['labelCorner'], d['xBearing'], partLine)
		item.fileLine = line
		self.currentStep.pli.layout[(d['filename'], d['color'])] = item
	
	def addCSI(self, line):
		if not self.currentStep:
			print "CSI Warning: Trying to create a CSI outside of a step.  Line %d" % (line[0])
			return
		
		#{'box': Box(*line[4:8]), 'center': Point(line[8], line[9])}
		d = lineToCSI(line)
		csi = self.currentStep.csi
		csi.fileLine = line
		csi.box = d['box']
		csi.center = d['center']

	def addPage(self, line):
		if self.currentPage and self.currentPage.steps == []:
			print "Page Warning: Empty page found on line %d. Ignoring Page %d" % (line[0], self.currentPage.number)
			self.pages.pop()
			self.currentPage = self.prevPage
		
		if self.currentPage and self.currentStep and self.currentStep.parts == []:
			print "Step Warning: Empty step found on line %d.  Ignoring Step %d" % (line[0], self.currentStep.number)
			self.currentPage.steps.pop()
			self.currentStep = self.currentStep.prevStep
			if self.currentPage.steps == []:
				print "Page Warning: Empty page found on line %d. Ignoring Page %d" % (line[0], self.currentPage.number)
				self.pages.pop()
				self.currentPage = self.prevPage
		
		self.prevPage = self.currentPage
		if self.firstPageNumber:
			self.currentPage = Page(self.firstPageNumber)
			self.firstPageNumber = None
		elif self.currentPage:
			self.currentPage = Page(self.currentPage.number + 1)
		else:
			self.currentPage = Page(1)
		self.currentPage.fileLine = line
		self.pages.append(self.currentPage)
	
	def addStep(self, line):
		if self.currentPage and self.currentStep and self.currentStep.parts == []: # Current step is empty - remove it and warn
			print "Step Warning: Empty step found on line %d.  Ignoring Step %d" % (line[0], self.currentStep.number)
			self.currentPage.steps.pop()
			self.currentStep = self.currentStep.prevStep
		
		if not self.currentPage:
			print "Error: Trying to add a step when there's no current page to add step to."
			return
			
		# Create a new step, set the current steps' nextStep to it, then make it the current step
		self.currentStep = Step(self.filename, self.currentStep, list(self.buffers), self)
		self.currentStep.fileLine = line
		self.currentPage.steps.append(self.currentStep)

	def addRotStep(self, line):
		if not self.currentStep:
			print "Rotation Step Error: Trying to create a rotation Step outside a valid Step. Line %d" % (line[0])
			return
		
		rotStep = lineToRotStep(line)
		if rotStep['state'] == ENDCommand:
			self.currentStep.rotStep = None
		else:
			self.currentStep.rotStep = rotStep

	def addPart(self, p, line):
		try:
			if self.currentPage:
				part = Part(p['filename'], p['color'], p['matrix'], p['ghost'], list(self.buffers), ldrawFile = self.ldrawFile, pageNumber = self.currentPage.number)
			else:
				part = Part(p['filename'], p['color'], p['matrix'], p['ghost'], list(self.buffers), ldrawFile = self.ldrawFile)
		except IOError:
			# TODO: This should be printed - commented out for debugging
			#print "Could not find file: %s - Ignoring." % p['filename']
			return
		
		part.ignorePLIState = self.ignorePLIState
		part.fileLine = line
		
		if self.currentStep:
			self.currentStep.addPart(part)
		else:
			self.parts.append(part)
		
		# TODO: If the same submodel is added more than once, page counts will be off - fix this
		if not part.ignorePLIState and part.partOGL.pages != []:
			self.currentPage.number = part.partOGL.pages[-1].number + 1
	
	def addPrimitive(self, p, shape):
		primitive = Primitive(p['color'], p['points'], shape, self.inverted ^ self.invertNext)
		self.primitives.append(primitive)
	
	def addBuffer(self, b):
		buffer, state = b.values()
			
		if state == BufferStore:
			self.buffers.append((buffer, self.currentStep.number))
			self.currentStep.csi.buffers = list(self.buffers)
		
		elif state == BufferRetrieve:
			if self.buffers[-1][0] == buffer:
				self.buffers.pop()
				self.currentStep.csi.buffers = list(self.buffers)
				if self.currentStep.parts != []:
					print "Buffer Exchange Error.  Restoring a buffer in Step ", self.currentStep.number, " after adding pieces to step.  Pieces will never be drawn."
			else:
				print "Buffer Exchange Error.  Last stored buffer: ", self.buffers[-1][0], " but trying to retrieve buffer: ", buffer

	def setPLIState(self, line):
		
		state = lineToLPubPLIState(line)
		if self.ignorePLIState == state:
			if state:
				print "PLI Ignore Error: Begnining PLI IGN when already begun.  Line: ", line[0]
			else:
				print "PLI Ignore Error: Ending PLI IGN when no valid PLI IGN had begun. Line: ", line[0]
		else:
			self.ignorePLIState = state
	
	def createOGLDisplayList(self):
		""" Initialize this part's display list.  Expensive call, but called only once. """
		if self.oglDispID != UNINIT_OGL_DISPID:
			return
		
		# Ensure any pages and steps in this part have been initialized
		for page in self.pages:
			for step in page.steps:
				step.csi.createOGLDisplayList()
		
		# Ensure any parts in this part have been initialized
		for part in self.parts:
			if part.partOGL.oglDispID == UNINIT_OGL_DISPID:
				part.partOGL.createOGLDisplayList()
		
		self.oglDispID = glGenLists(1)
		glNewList(self.oglDispID, GL_COMPILE)
		
		for page in self.pages:
			for step in page.steps:
				step.csi.callOGLDisplayList()
		
		for part in self.parts:
			part.callOGLDisplayList()
		
		for primitive in self.primitives:
			primitive.callOGLDisplayList()
		
		glEndList()

	def draw(self):
		glCallList(self.oglDispID)
	
	def initSize_checkRotation(self):
		# TODO: Create a static list of all standard parts along with the necessary rotation needed
		# to get them from their default file rotation to the rotation seen in Lego's PLIs.
		pass

	def dimensionsToString(self):
		if self.isPrimitive:
			return ""
		return "%s %d %d %d %d %d %d\n" % (self.filename, self.width, self.height, self.center.x, self.center.y, self.leftInset, self.bottomInset)

	def initSize(self, size):
		"""
		Initialize this part's display width, height, empty corner insets and center point.
		To do this, draw this part to the already initialized GL Frame Buffer Object.
		These dimensions are required to properly lay out PLIs and CSIs.
		Note that an appropriate FBO *must* be initialized before calling initSize.
		
		Parameters:
			size: Width & height of FBO to render to, in pixels.  Note that FBO is assumed square
		
		Returns:
			True if part rendered successfully.
			False if the part has been rendered partially or wholly out of frame.
		"""
		
		# TODO: If a part is rendered at a size > 256, draw it smaller in the PLI - this sounds like a great way to know when to shrink a PLI image...
		# TODO: Check how many pieces would be rendered successfully at 128 - if significant, test adding that to size list, see if it speeds part generation up
		if self.isPrimitive:
			return True  # Primitive parts need not be sized
		
		params = GLHelpers.initImgSize(size, size, self.oglDispID, False, self.filename)
		if params is None:
			return False
		
		# TODO: update some kind of load status bar her - this function is *slow*
		print self.filename + " - size: %d" % (size)
		
		self.width, self.height, self.center, self.leftInset, self.bottomInset = params
		return True
	
	def renderToPov(self, color = None):
		
		filename = None
		if self.ldArrayStartEnd:
			# This is a submodel in main file - need to write this to its own .dat
			filename = self.ldrawFile.writeLinesToDat(self.filename, *self.ldArrayStartEnd)
		
		# Render this part to a pov file and a final png image
		camera = GLHelpers.getPLICamera()
		self.pngFile = self.ldrawFile.createPov(self.width, self.height, filename, camera, self.center, color)
	
	def boundingBox(self):
		# TODO: remove this check, and this entire method, once it is no longer ever called
		print "Error: trying to determine a bounding box for a partOGL!: %s" % (self.filename)
		return None

class Part:
	"""
	Represents one 'concrete' part, ie, an 'abstract' part (partOGL), plus enough
	info to draw that abstract part in context of a model, ie color, positional 
	info, containing buffer state, etc.  In other words, Part represents everything
	that could be different between two 2x4 bricks in a model.
	"""
	
	def __init__(self, filename, color = 16, matrix = None, ghost = False, buffers = [], invert = False, ldrawFile = None, isMainModel = False, pageNumber = None):
		
		self.color = color
		self.matrix = matrix
		self.ghost = ghost
		self.buffers = buffers  # [(bufID, stepNumber)]
		self.inverted = invert
		self.ignorePLIState = False
		self.fileLine = None 
		
		self.translateCallback = None
		
		if filename in partDictionary:
			self.partOGL = partDictionary[filename]
		else:
			self.partOGL = partDictionary[filename] = PartOGL(filename, ldrawFile, isMainModel, pageNumber)
		
		self.name = self.partOGL.name

	def translate(self, x, y, z):
		self.matrix[12] = x
		self.matrix[13] = y
		self.matrix[14] = z
		
		if self.ghost:
			self.fileLine[5] = str(x)
			self.fileLine[6] = str(y)
			self.fileLine[7] = str(z)
		else:
			self.fileLine[3] = str(x)
			self.fileLine[4] = str(y)
			self.fileLine[5] = str(z)
		
		if self.translateCallback:
			self.translateCallback()

	def shouldBeDrawn(self, currentBuffer):
		
		if len(self.buffers) < 1:
			return True  # Piece not in any buffer - draw always
		
		# This piece is in a buffer
		if (currentBuffer is None) or (len(currentBuffer) < 1):
			return False  # Piece in a buffer, but no current buffer - don't draw
		
		if self.buffers == currentBuffer: # Piece and current buffer match - draw
			return True
		
		return False # Piece and current buffer don't match - don't draw

	def callOGLDisplayList(self, currentBuffer = None):
		
		if not self.shouldBeDrawn(currentBuffer):
			return
		
		# must be called inside a glNewList/EndList pair
		color = convertToRGBA(self.color)
		
		if color != CurrentColor:
			glPushAttrib(GL_CURRENT_BIT)
			if len(color) == 3:
				glColor3fv(color)
			elif len(color) == 4:
				glColor4fv(color)
		
		if self.inverted:
			glPushAttrib(GL_POLYGON_BIT)
			glFrontFace(GL_CW)
		
		if self.matrix:
			glPushMatrix()
			glMultMatrixf(self.matrix)
			
		glCallList(self.partOGL.oglDispID)
		
		if self.matrix:
			glPopMatrix()
		
		if self.inverted:
			glPopAttrib()
		
		if color != CurrentColor:
			glPopAttrib()

	def draw(self, context, winWidth, winHeight):
		global _docWidth, _docHeight
		
		# Draw an empty page, just for a nice looking frame
		page = Page(0)
		page.initPageSize(winWidth, winHeight, context)
		page.drawPage(context)
		
		x = (_docWidth / 2.) - (self.partOGL.width / 2.)
		y = (_docHeight / 2.) - (self.partOGL.height / 2.)
		
		GLHelpers.adjustGLViewport(x, y, self.partOGL.width, self.partOGL.height)
		glLoadIdentity()
		GLHelpers.rotateToDefaultView(self.partOGL.center.x, self.partOGL.center.y, 0.0)
		
		self.partOGL.draw()
		
		pixels = glReadPixels (0, 0, winWidth, winHeight, GL_RGBA,  GL_UNSIGNED_BYTE)
		surface = cairo.ImageSurface.create_for_data(pixels, cairo.FORMAT_ARGB32, winWidth, winHeight, winWidth * 4)
		context.set_source_surface(surface)
		context.paint()
		surface.finish()	

	def boundingBox(self):
		# TODO figure out a way to nicely show selected parts.  Maybe render all other parts mostly transparent?  Or a semi transparent colored overlay?
		return None

class Primitive:
	"""
	Not a primitive in the LDraw sense, just a single line/triangle/quad.
	Used mainly to construct an OGL display list for a set of points.
	"""
	
	def __init__(self, color, points, type, invert = True):
		self.color = color
		self.type = type
		self.points = points
		self.inverted = invert

	# TODO: using numpy for all this would probably work a lot better
	def addNormal(self, p1, p2, p3):
		Bx = p2[0] - p1[0]
		By = p2[1] - p1[1]
		Bz = p2[2] - p1[2]
		
		Cx = p3[0] - p1[0]
		Cy = p3[1] - p1[1]
		Cz = p3[2] - p1[2]
		
		Ax = (By * Cz) - (Bz * Cy)
		Ay = (Bz * Cx) - (Bx * Cz)
		Az = (Bx * Cy) - (By * Cx)
		l = math.sqrt((Ax*Ax)+(Ay*Ay)+(Az*Az))
		if l != 0:
			Ax /= l
			Ay /= l
			Az /= l
		return [Ax, Ay, Az]
	
	def callOGLDisplayList(self):
		
		# must be called inside a glNewList/EndList pair
		color = convertToRGBA(self.color)
		
		if color != CurrentColor:
			glPushAttrib(GL_CURRENT_BIT)
			if len(color) == 3:
				glColor3fv(color)
			elif len(color) == 4:
				glColor4fv(color)
		
		p = self.points
		
		if self.inverted:
			normal = self.addNormal(p[6:9], p[3:6], p[0:3])
			#glBegin( GL_LINES )
			#glVertex3f(p[3], p[4], p[5])
			#glVertex3f(p[3] + normal[0], p[4] + normal[1], p[5] + normal[2])
			#glEnd()
			
			glBegin( self.type )
			glNormal3fv(normal)
			if self.type == GL_QUADS:
				glVertex3f( p[9], p[10], p[11] )
			glVertex3f( p[6], p[7], p[8] )
			glVertex3f( p[3], p[4], p[5] )
			glVertex3f( p[0], p[1], p[2] )
			glEnd()
		else:
			normal = self.addNormal(p[0:3], p[3:6], p[6:9])
			#glBegin( GL_LINES )
			#glVertex3f(p[3], p[4], p[5])
			#glVertex3f(p[3] + normal[0], p[4] + normal[1], p[5] + normal[2])
			#glEnd()
			
			glBegin( self.type )
			glNormal3fv(normal)
			glVertex3f( p[0], p[1], p[2] )
			glVertex3f( p[3], p[4], p[5] )
			glVertex3f( p[6], p[7], p[8] )
			if self.type == GL_QUADS:
				glVertex3f( p[9], p[10], p[11] )
			glEnd()
		
		if color != CurrentColor:
			glPopAttrib()