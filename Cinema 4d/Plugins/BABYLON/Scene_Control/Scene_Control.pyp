import c4d
import os
import sys
import json
import math
import re

from c4d import gui, documents, utils, storage, plugins, bitmaps, Vector
from math import pi

PLUGIN_ID = 1054498
__version__ = "1.1"
__plugin_title__ = "BABYLON Scene Control"
__author__ = "Pryme8"

#=================================
#SCENE CONTROL DECLATRIONS
#=================================
BJS_SCENE_AUTO_CLEAR             = 10000
BJS_SCENE_CLEAR_COLOR            = 10001
BJS_SCENE_CLEAR_ALPHA            = 100010
BJS_SCENE_AMBIENT_COLOR          = 10002
BJS_SCENE_GRAVITY                = 10003
BJS_SCENE_ACTIVE_CAMERA          = 10004
BJS_SCENE_COLLISIONS_ENABLED     = 10005
BJS_SCENE_PHYSICS_ENABLED        = 10006
BJS_SCENE_PHYSICS_GRAVITY        = 10007
BJS_SCENE_PHYSICS_ENGINE         = 10008
BJS_SCENE_AUTO_ANIMATE           = 10009
BJS_SCENE_AUTO_ANIMATE_FROM      = 10010
BJS_SCENE_AUTO_ANIMATE_TO        = 10011
BJS_SCENE_AUTO_ANIMATE_LOOP      = 10012
BJS_SCENE_AUTO_ANIMATE_SPEED     = 10013

BJS_SCENE_GLOBAL_SCALE           = 10014

BJS_EXPORT_SCENE_TEMPLATE = 2000
#---------------------------------

#=================================
#JSON Encoder Class
#=================================
class ComplexEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj,'reprJSON'):
            return obj.reprJSON()
        else:
            return json.JSONEncoder.default(self, obj)
#---------------------------------

#=================================
#quick converters
#=================================
def Vec3Array(v):
    return [ v.x, v.y, v.z ]
    
def Vec3ArrayScaled(v, s):
    return [ v.x * s, v.y * s, v.z * s ]    
 

def getValue(op, v):
    return eval('op[c4d.'+v+']')

def Vec2(v):
    return {'x':v[0],'y':v[1]}

def Vec3(v):
    return {'x':v[0], 'y':v[1], 'z':v[2]}

def rotationAxis(op):
    mat = utils.MatrixToRotAxis(op.GetMg())    
    return {'x':mat[0][0], 'y':mat[0][1], 'z':mat[0][2], 'a': mat[1]}

def sVec3(v):
    return {'x':scale(v[0]),'y':scale(v[1]),'z':scale(v[2])}

def Orientation(axes):
    return ([{'x':1,'y':0,'z':0},{'x':-1,'y':0,'z':0},{'x':0,'y':1,'z':0},{'x':0,'y':-1,'z':0},{'x':0,'y':0,'z':1},{'x':1,'y':0,'z':-1}])[axes]

def LightTypes(t):
    return (["Point", "Spot", "Directional", "Directional"])[t]
#---------------------------------

#=================================
#BASIC TRANSFORMS CLASS
#=================================
class Transforms:
    def __init__(self):        
        self.position = None
        self.rotation = None
        self.scale = None
        
    def reprJSON(self):
        return dict(position=self.position, rotation=self.rotation, scale=self.scale)    
#--------------------------------- 

#=================================
#NODE CLASS
#=================================
class Node:
    def __init__(self):
        self.type = 'node'
        self.subType = 'none'
        self.name = 'NewNode'
        self.transforms = Transforms()        
        self.children = []
        self.attributes = {}
        
    def __getitem__(self, arg):
        return str(arg)
    
    def parseObject(self, op):
        type = op.GetTypeName()
        if (
            type == "Cube" or
            type == "Plane" or
            type == "Torus" or
            type == "Sphere"
        ):            
            self.type = "Primitive"
            if type == "Plane":
                self.subType = "Ground"
            else:
                self.subType = type         
        else:    
            self.type = type            
                    
        self.name = op.GetName()
        
        #setTransforms          
        self.transforms.position = Vec3(op.GetAbsPos())  
        self.transforms.rotation = rotationAxis(op)
        self.transforms.scale = Vec3(op.GetAbsScale())
       
        description = op.GetDescription(c4d.DESCFLAGS_DESC_0)
        tags = op.GetTags()
        
        #CAMERAS
        if self.type == "Camera":
            tempTarget = c4d.BaseObject(c4d.Ocube)          
            tempTarget.InsertUnder(op)
            tempTarget.SetRelPos(c4d.Vector(0, 0, 2000))
            mat = tempTarget.GetMg()
            c4d.EventAdd()      
            
            self.attributes['CAMERA_TARGET'] =  Vec3(tempTarget.GetRelPos()*mat)
            
            tempTarget.Remove()
            for tag in tags:
                td = tag.GetDescription(c4d.DESCFLAGS_DESC_0)
                for bc, paramid, groupid in td:                    
                    if (
                        bc[c4d.DESC_IDENT] == "BJS_CAMERA_MAKE_DEFAULT" or
                        bc[c4d.DESC_IDENT] == "BJS_CAMERA_ATTACH_CONTROLS" or
                        bc[c4d.DESC_IDENT] == "BJS_CAMERA_SPEED" or
                        bc[c4d.DESC_IDENT] == "BJS_CAMERA_ANGULAR_SENSIBILITY"
                    ):
                        self.attributes[bc[c4d.DESC_IDENT]] = tag[paramid[0].id]
                        
                    elif bc[c4d.DESC_IDENT] == "BJS_CAMERA_Z_CLIP":
                        self.attributes[bc[c4d.DESC_IDENT]] = Vec2(tag[paramid[0].id])
        #-----------------
        
        #LIGHTS
        elif self.type == "Light":            
            for bc, paramid, groupid in description:
                if bc[c4d.DESC_IDENT] == "LIGHT_COLOR":                    
                    self.attributes[bc[c4d.DESC_IDENT]] = Vec3(getValue(op, bc[c4d.DESC_IDENT]))
                elif bc[c4d.DESC_IDENT] == "LIGHT_TYPE":
                    self.attributes[bc[c4d.DESC_IDENT]] = LightTypes(getValue(op, bc[c4d.DESC_IDENT]))
                elif bc[c4d.DESC_IDENT] == "LIGHT_BRIGHTNESS":
                    self.attributes[bc[c4d.DESC_IDENT]] = getValue(op, bc[c4d.DESC_IDENT])
        
            for tag in op.GetTags():
                td = tag.GetDescription(c4d.DESCFLAGS_DESC_0)
                for bc, paramid, groupid in td:
                     if bc[c4d.DESC_IDENT] == "BJS_LIGHT_SPECULAR":
                          self.attributes[bc[c4d.DESC_IDENT]] = Vec3(getValue(tag, bc[c4d.DESC_IDENT]))
        #-----------------
        
        #PRIMITIVES
        if self.type == "Primitive":
            for bc, paramid, groupid in description:
                if bc[c4d.DESC_IDENT] != None:
                    if (str(bc[c4d.DESC_IDENT]).split("_"))[0] == "PRIM":
                        _d = eval('op[c4d.'+bc[c4d.DESC_IDENT]+']')
                        if isinstance(_d, c4d.Vector):
                            self.attributes[bc[c4d.DESC_IDENT]] = Vec3(_d)
                        else:
                            if bc[c4d.DESC_IDENT] == 'PRIM_AXIS':
                                self.attributes[bc[c4d.DESC_IDENT]] = Orientation(_d)
                            else:  
                                self.attributes[bc[c4d.DESC_IDENT]] = _d
        #-----------------
        
        #POLYGONS
        if self.type == "Polygon":
            #Prep
            _op = op.GetClone()            
            io = _op.GetAllPolygons()
            po = _op.GetAllPoints()
            
            positions = []
            indices = []
            uv = []
      
            for i in io:
                indices.extend([i.a, i.d, i.c, i.a, i.c, i.b])           
            
            for p in po:
                positions.extend([p.x, p.y, p.z])
            
            
            self.attributes["Buffers"] = {
                "positions" : positions,
                "indices"   : indices,
            }
            
            uvwtag = op.GetTag(c4d.Tuvw)
            if uvwtag is not None:            
                nbr = utils.Neighbor()
                nbr.Init(op)
                pnt_ids = [id for id, val in enumerate(po)]
                for pid in pnt_ids:
                    polys = nbr.GetPointPolys(pid)
                    if polys is not None:
                        cpoly = op.GetPolygon(polys[0])
                        uvwdict = uvwtag.GetSlow(polys[0])
                        if pid == cpoly.a:
                            uv.extend([uvwdict['a'].x, uvwdict['a'].y])
                        elif pid == cpoly.b:
                            uv.extend([uvwdict['b'].x, uvwdict['b'].y])
                        elif pid == cpoly.c:
                            uv.extend([uvwdict['c'].x, uvwdict['c'].y])
                        elif pid == cpoly.d:
                            uv.extend([uvwdict['d'].x, uvwdict['d'].y])
                    
                self.attributes["Buffers"]["uv"] = uv
            
        #----------------- 
        
        
        for tag in tags:            
            if tag.GetTypeName() == "BJS_Standard_Material":
                self.attributes['material'] = {
                    "type" : "StandardMaterial"
                }
                td = tag.GetDescription(c4d.DESCFLAGS_DESC_0)
                for bc, paramid, groupid in td:                    
                    if (
                        bc[c4d.DESC_IDENT] == "BJS_MATERIAL_NAME"
                    ):
                        self.attributes['material'][bc[c4d.DESC_IDENT]] = tag[paramid[0].id]
                    elif (
                        bc[c4d.DESC_IDENT] == "BJS_MATERIAL_COLOR_AMBIENT" or
                        bc[c4d.DESC_IDENT] == "BJS_MATERIAL_COLOR_DIFFUSE" or
                        bc[c4d.DESC_IDENT] == "BJS_MATERIAL_COLOR_EMISSIVE" or
                        bc[c4d.DESC_IDENT] == "BJS_MATERIAL_COLOR_SPECULAR"
                    ):
                        self.attributes['material'][bc[c4d.DESC_IDENT]] = Vec3(tag[paramid[0].id])
                    
            #CHECK FOR GLOBAL TAGS DESCRIPTIONS
            td = tag.GetDescription(c4d.DESCFLAGS_DESC_0)
            for bc, paramid, groupid in td:                    
                if (
                    bc[c4d.DESC_IDENT] == "BJS_EXPOSE_VARIABLE" or
                    bc[c4d.DESC_IDENT] == "BJS_EXPOSE_GLOBAL" or
                    bc[c4d.DESC_IDENT] == "BJS_VARIABLE_NAME"
                ):
                    self.attributes[bc[c4d.DESC_IDENT]] = tag[paramid[0].id]
           
        #----------------- 
    
    def reprJSON(self):
        return dict(type=self.type, subType=self.subType, name=self.name, transforms=self.transforms, attributes=self.attributes, children=self.children)
#---------------------------------

class Camera:
    def __init__(self, node, scene, parent):
            nData = node.GetDataInstance()
            tags = node.GetTags()
            
            cTag = None
            for tag in tags:
                print tag.GetTypeName()
                if tag.GetTypeName() == "BJS_Camera_Tag":
                    cTag = tag
            
            tData = cTag.GetDataInstance()
            
            self.name = node.GetName()
            self.id = node.GetName()            
            
            #BJS_CAMERA_TYPE_FREE
            if tData[c4d.BJS_CAMERA_TYPE] == 100011:
                self.type = 'UniversalCamera'
            #BJS_CAMERA_TYPE_ARC
            elif tData[c4d.BJS_CAMERA_TYPE] == 100012:
                self.type = 'ArcRotateCamera'
            #BJS_CAMERA_TYPE_FOLLOW
            elif tData[c4d.BJS_CAMERA_TYPE] == 100013:
                self.type = 'FollowCamera'
                
            self.tags = ""
            if parent is not False:
                self.parentId = parent.id
            else:
                self.parentId = ""
            
            #lockedTargetId 
            
            self.position = Vec3ArrayScaled( node.GetAbsPos(), scene.globalScale )
            
            tempTarget = c4d.BaseObject(c4d.Ocube)          
            tempTarget.InsertUnder( node )
            tempTarget.SetRelPos(c4d.Vector(0, 0, 2000))
            mat = tempTarget.GetMg() 
            
            self.target =  Vec3ArrayScaled(tempTarget.GetRelPos() * mat , scene.globalScale)
            
            tempTarget.Remove()
            
            #if tData[c4d.BJS_CAMERA_MAKE_ACTIVE] == True:
            if scene.activeCamera is None:
                scene.activeCamera = self.name
            
            
            #alpha
            #beta
            #radius
            #eye_space
            
            #heightOffset
            #rotationOffset            
            #cameraRigMode
            
            self.fov = tData[c4d.BJS_CAMERA_FOV]
            self.minZ = tData[c4d.BJS_CAMERA_MINZ]
            self.maxZ = tData[c4d.BJS_CAMERA_MAXZ]
            self.speed = tData[c4d.BJS_CAMERA_SPEED]
            self.inertia = tData[c4d.BJS_CAMERA_INERTIA]
            self.checkCollisions = tData[c4d.BJS_CAMERA_CHECK_COLLISIONS]
            self.applyGravity = tData[c4d.BJS_CAMERA_FOV]
            self.ellipsoid = tData[c4d.BJS_CAMERA_FOV]
            self.attachControls = tData[c4d.BJS_CAMERA_ATTACH_CONTROLS]
            
            self.animations = []
            self.autoAnimate = tData.GetBool( c4d.BJS_CAMERA_AUTO_ANIMATE )
            self.autoAnimateFrom = tData.GetLong( c4d.BJS_CAMERA_AUTO_ANIMATE_FROM )
            self.autoAnimateTo = tData.GetLong( c4d.BJS_CAMERA_AUTO_ANIMATE_TO )
            self.autoAnimateLoop = tData.GetBool( c4d.BJS_CAMERA_AUTO_ANIMATE_LOOP )
            self.autoAnimateSpeed = tData.GetFloat( c4d.BJS_CAMERA_AUTO_ANIMATE_SPEED )
            
            self.inputmgr = []
      
    
    def __getitem__(self, arg):
        return str(arg)
    
    def reprJSON(self):
        return dict(
                name = self.name,
                id = self.id,
                type = self.type,
                tags = self.tags,
                parentId = self.parentId,
                #lockedTargetId = self.lockedTargetId,
                position = self.position,
                target = self.target,
                #alpha = self.alpha,
                #beta = self.beta,
                #radius = self.radius,
                #eye_space = self.eye_space,
                #heightOffset = self.heightOffset,
                #rotationOffset = self.rotationOffset,
                #cameraRigMode = self.cameraRigMode,
                fov = self.fov,
                minZ = self.minZ,
                maxZ = self.maxZ,
                speed = self.speed,
                inertia = self.inertia,
                checkCollisions = self.checkCollisions,
                applyGravity = self.applyGravity,
                ellipsoid = self.ellipsoid,
                attachControls = self.attachControls,
                animations = self.animations,
                autoAnimate = self.autoAnimate,
                autoAnimateFrom = self.autoAnimateFrom,
                autoAnimateTo = self.autoAnimateTo,
                autoAnimateLoop = self.autoAnimateLoop,
                autoAnimateSpeed = self.autoAnimateSpeed,
                inputmgr = self.inputmgr                
            ) 

class Light:
    def __init__(self, node, scene, parent):
            nData = node.GetDataInstance()
            tags = node.GetTags()
            
            lightTag = False
            for tag in tags:
                #print tag.GetTypeName()
                if tag.GetTypeName() == "BJS_Light_Tag":
                    lightTag = tag            
            
            self.name = node.GetName()
            self.id = node.GetName()
            
            self.specularColor  = [1,1,1]
            self.diffuseColor   = [1,1,1]
            self.intensity      = 1
            self.range          = None
            self.radius         = None           
            self.direction      = None
            self.angle          = None
            self.exponent       = None
            self.groundColor    = None
            
            self.excludedMeshesIds = None
            self.includedOnlyMeshesIds = None
            
            if lightTag:
                lData = lightTag.GetDataInstance()
                self.specularColor = Vec3Array(lightTag[c4d.BJS_LIGHT_SPECULAR])
            
            self.type = node[c4d.LIGHT_TYPE]
            #Establish what type.
            #C4D :
            #0  = Point Light
            #1  = Spot Light
            #3  = Directional
            #BJS :
            #LIGHTTYPEID_POINTLIGHT = 0;
            #LIGHTTYPEID_DIRECTIONALLIGHT = 1;
            #LIGHTTYPEID_SPOTLIGHT = 2;
            #LIGHTTYPEID_HEMISPHERICLIGHT = 3;            
            if self.type == 1:
                #Spot Light
                self.type = 2
                if lightTag is not False:
                    self.exponent = lightTag[c4d.BJS_LIGHT_EXPONENT]
                
                tempTarget = c4d.BaseObject(c4d.Ocube)          
                tempTarget.InsertUnder( node )
                tempTarget.SetRelPos(c4d.Vector(0, 0, 1))
                gPos = tempTarget.GetRelPos() * tempTarget.GetMg()            
                tempTarget.Remove()
                normal = gPos - node.GetAbsPos()
                self.direction  = Vec3Array(normal.GetNormalized())
                
            elif self.type == 3:
                if lightTag is False:
                    self.type = 1
                else:
                    if lightTag[c4d.BJS_LIGHT_MAKE_HEMISPHERIC] is False:
                        self.type = 1
                    else:
                        self.groundColor = Vec3Array(lightTag[c4d.BJS_LIGHT_GROUND_COLOR])                    
                        tempTarget = c4d.BaseObject(c4d.Ocube)          
                        tempTarget.InsertUnder( node )
                        tempTarget.SetRelPos(c4d.Vector(0, -1, 0))
                        gPos = tempTarget.GetRelPos() * tempTarget.GetMg()            
                        tempTarget.Remove()
                        normal = gPos().sub(node.GetAbsPos())
                        self.direction  = Vec3Array(normal.GetNormalized())
            else:
                self.type = 0
                #Area light not supported.

            self.diffuseColor = Vec3Array(node[c4d.LIGHT_COLOR])
            self.intensity = node[c4d.LIGHT_BRIGHTNESS]
               
            self.tags = ""
            if parent is not False:
                self.parentId = parent.id
            else:
                self.parentId = ""
            
            self.position = Vec3ArrayScaled( node.GetAbsPos(), scene.globalScale )

            if node[c4d.LIGHT_DETAILS_FALLOFF] == 0:
                self.range = float("inf")
            else:
                self.range = node[c4d.LIGHT_DETAILS_OUTERDISTANCE]
            
            
            inExlist = node[c4d.LIGHT_EXCLUSION_LIST]
            inExStringList = []
            
            for i in range(inExlist.GetObjectCount()):
                obj = inExlist.ObjectFromIndex( documents.GetActiveDocument(), i)
                inExStringList.append( obj.GetName() )

            if len(inExStringList) > 0:
                if node[c4d.LIGHT_EXCLUSION_MODE] == 0:
                    #include list
                    self.includedOnlyMeshesIds = inExStringList
                else:
                    #exclude list
                    self.excludedMeshesIds = inExStringList
            
            self.animations = []
            if lightTag:
                self.autoAnimate = lightTag.GetBool( c4d.BJS_LIGHT_AUTO_ANIMATE )
                self.autoAnimateFrom = lightTag.GetLong( c4d.BJS_LIGHT_AUTO_ANIMATE_FROM )
                self.autoAnimateTo = lightTag.GetLong( c4d.BJS_LIGHT_AUTO_ANIMATE_TO )
                self.autoAnimateLoop = lightTag.GetBool( c4d.BJS_LIGHT_AUTO_ANIMATE_LOOP )
                self.autoAnimateSpeed = lightTag.GetFloat( c4d.BJS_LIGHT_AUTO_ANIMATE_SPEED )
            else:
                self.autoAnimate = False
                self.autoAnimateFrom = 0
                self.autoAnimateTo = 0
                self.autoAnimateLoop = False
                self.autoAnimateSpeed = 1            
    
    def __getitem__(self, arg):
        return str(arg)
    
    def reprJSON(self):
        return dict(
                name =              self.name,
                id =                self.id,
                type =              self.type,
                tags =              self.tags,
                parentId =          self.parentId,
                position =          self.position,
                direction =         self.direction,
                diffuseColor =      self.diffuseColor,
                specularColor =     self.specularColor,
                groundColor =       self.groundColor,
                intensity =         self.intensity,
                angle =             self.angle,
                exponent =          self.exponent,
                animations =        self.animations,
                autoAnimate =       self.autoAnimate,
                autoAnimateFrom =   self.autoAnimateFrom,
                autoAnimateTo =     self.autoAnimateTo,
                autoAnimateLoop =   self.autoAnimateLoop,
                autoAnimateSpeed =  self.autoAnimateSpeed            
            ) 

#=================================
#Recursion Function
#=================================
def recurse_hierarchy(op, scene, parent):    
    while op:
        element = None
        for tag in op.GetTags():
            #print tag.GetTypeName()
            if tag.GetTypeName() == "BJS_Ignore_Tag":
                if tag[c4d.BJS_IGNORE_BOOL] is True:
                    return
                
        type = op.GetTypeName()
        
        if type == "Camera":
            camera = Camera(op, scene, parent)
            scene.cameras.append( camera )
            element = camera
        
        if type == "Light":
            light = Light(op, scene, parent)
            scene.lights.append( light )
            element = light   
                
        if(op.GetDown()):
            recurse_hierarchy(op.GetDown(), scene, element)
        
        op = op.GetNext()
    return scene
#---------------------------------

class Scene:
    def __init__(self, node):
        data = node.GetDataInstance()
        self.autoClear = data.GetBool( BJS_SCENE_AUTO_CLEAR )
        self.globalScale = 1/data.GetFloat( BJS_SCENE_GLOBAL_SCALE )
        self.clearColor = Vec3Array(data.GetVector( BJS_SCENE_CLEAR_COLOR ))
        self.clearColor = [ self.clearColor[0], self.clearColor[1], self.clearColor[2], data.GetFloat( BJS_SCENE_CLEAR_ALPHA ) ]
        self.ambientColor = Vec3Array(data.GetVector( BJS_SCENE_AMBIENT_COLOR ))
        self.gravity = Vec3Array(data.GetVector( BJS_SCENE_GRAVITY ))
        self.cameras = []
        self.activeCamera = None
        self.lights = []
        self.reflectionProbes = []
        self.materials = []
        self.geometries = []
        self.meshes = []
        self.multiMaterials = []
        self.shadowGenerators = []
        self.skeletons = []
        self.particleSystems = []
        self.lensFlareSystems = []
        self.actions = []
        self.sounds = []
        self.collisionsEnabled = data.GetBool( BJS_SCENE_COLLISIONS_ENABLED )
        self.physicsEnabled = data.GetBool( BJS_SCENE_PHYSICS_ENABLED )
        self.physicsGravity = Vec3Array(data.GetVector( BJS_SCENE_PHYSICS_GRAVITY ))
        self.physicsEngine = data.GetString( BJS_SCENE_PHYSICS_ENGINE )
        self.animations = []
        self.autoAnimate = data.GetBool( BJS_SCENE_AUTO_ANIMATE )
        self.autoAnimateFrom = data.GetLong( BJS_SCENE_AUTO_ANIMATE_FROM )
        self.autoAnimateTo = data.GetLong( BJS_SCENE_AUTO_ANIMATE_TO )
        self.autoAnimateLoop = data.GetBool( BJS_SCENE_AUTO_ANIMATE_LOOP )
        self.autoAnimateSpeed = data.GetFloat( BJS_SCENE_AUTO_ANIMATE_SPEED )        
    
    def __getitem__(self, arg):
        return str(arg)
    
    def reprJSON(self):
        return dict( 
                autoClear=self.autoClear,
                clearColor=self.clearColor,
                ambientColor=self.ambientColor,
                gravity=self.gravity,
                cameras=self.cameras,
                activeCamera=self.activeCamera,
                lights=self.lights,
                reflectionProbes=self.reflectionProbes,
                materials=self.materials,
                geometries=self.geometries,
                meshes=self.meshes,
                multiMaterials=self.multiMaterials,
                shadowGenerators=self.shadowGenerators,
                skeletons=self.skeletons,
                particleSystems=self.particleSystems,
                lensFlareSystems=self.lensFlareSystems,
                actions=self.actions,
                sounds=self.sounds,
                collisionsEnabled=self.collisionsEnabled,
                physicsEnabled=self.physicsEnabled,
                physicsGravity=self.physicsGravity,
                physicsEngine=self.physicsEngine,
                animations=self.animations,
                autoAnimate=self.autoAnimate,
                autoAnimateFrom=self.autoAnimateFrom,
                autoAnimateTo=self.autoAnimateTo,
                autoAnimateLoop=self.autoAnimateLoop,
                autoAnimateSpeed=self.autoAnimateSpeed
            ) 

#=================================
#PARSED DATA CLASS
#=================================
class parsedScene:
    def __init__(self, op):
        self.nodes = []
        self.attributes = {}        
        description = op.GetDescription(c4d.DESCFLAGS_DESC_0)
        
        for bc, paramid, groupid in description:
            if bc[c4d.DESC_IDENT] != None:
                 if (
                    bc[c4d.DESC_IDENT] == "BJS_SCENE_CLEARCOLOR" or
                    bc[c4d.DESC_IDENT] == "BJS_SCENE_AMBIENTCOLOR" 
                 ):
                    self.attributes[bc[c4d.DESC_IDENT]] = Vec3(getValue(op, bc[c4d.DESC_IDENT]))
                 elif (
                    bc[c4d.DESC_IDENT] == "BJS_SCENE_CLEARALPHA" or
                    bc[c4d.DESC_IDENT] == "BJS_SCENE_MAX_LIGHTS" 
                 ):
                    self.attributes[bc[c4d.DESC_IDENT]] = getValue(op, bc[c4d.DESC_IDENT])
    
    def __getitem__(self, arg):
        return str(arg)
    
    def reprJSON(self):
        return dict( 
            nodes=self.nodes,
            attributes=self.attributes
            )    
#---------------------------------

#=================================
#Parsing Function
#=================================
def startParse(op):
    scene = Scene(op)
    scene = recurse_hierarchy(op.GetDown(), scene, False)
    return scene
#---------------------------------

def cleanArrays(data):
    regex = r"""
	(?:\[(?:[^]]+)\])
	"""
    matches = re.finditer(regex, data, re.MULTILINE | re.VERBOSE)    
    diff = 0    
    for i, m in enumerate(matches, start=0):
        s = m.start(0) - diff
        e = m.end(0) - diff        
        clean = m.group(0).replace(' ', '').replace('\n', '').replace('\r', '')        
        diff = diff + (len(m.group(0)) - len(clean))
        a = data[0:s]
        b = data[e:len(data)]        
        data = a+clean+b
    return data

#=================================
#SCENE CONTROL CLASS
#=================================
class Scene_Control(plugins.ObjectData):
    
    def Init(self, node):
        #Scene Defaults
        data = node.GetDataInstance()
        data.SetBool( BJS_SCENE_AUTO_CLEAR, True)
        data.SetVector( BJS_SCENE_CLEAR_COLOR, Vector(0.2,0.2,0.5))
        data.SetFloat( BJS_SCENE_CLEAR_ALPHA, 1)
        data.SetVector( BJS_SCENE_AMBIENT_COLOR, Vector(0,0,0))
        data.SetVector( BJS_SCENE_GRAVITY, Vector(0,-9.81,0))
        data.SetBool( BJS_SCENE_COLLISIONS_ENABLED, False)
        data.SetBool( BJS_SCENE_PHYSICS_ENABLED, False)
        data.SetVector( BJS_SCENE_PHYSICS_GRAVITY, Vector(0,-9.81,0))
        data.SetString( BJS_SCENE_PHYSICS_ENGINE, 'oimo')
        data.SetBool( BJS_SCENE_AUTO_ANIMATE, False)
        data.SetLong( BJS_SCENE_AUTO_ANIMATE_FROM, 0)
        data.SetLong( BJS_SCENE_AUTO_ANIMATE_TO, 0)
        data.SetBool( BJS_SCENE_AUTO_ANIMATE_LOOP, False)
        data.SetFloat( BJS_SCENE_AUTO_ANIMATE_SPEED, 1)        
        data.SetFloat( BJS_SCENE_GLOBAL_SCALE, 200 )        
         
        return True
        
    def Execute(self, node, doc, bt, priority, flags):
        return c4d.EXECUTIONRESULT_OK


    def Message(self, node, type, data):
        if type == c4d.MSG_DESCRIPTION_CHECKDRAGANDDROP:
            print data
            
        if type ==  c4d.MSG_DESCRIPTION_COMMAND:
            if data['id'][0].id == BJS_EXPORT_SCENE_TEMPLATE:
                self.Export(node)        
        
        
        return True        


    def Export(self, node):        
            data = json.dumps((startParse(node)).reprJSON(), sort_keys=True, indent=4, separators=(',', ': '), cls=ComplexEncoder)
            data = cleanArrays(data)          
            
            #print data
            
            filePath = storage.LoadDialog(title="Save as Babylon File", flags=c4d.FILESELECT_SAVE, force_suffix="babylon")
            if filePath is None:
                return
            #open file
            f = open(filePath,"w")
            f.write(data)
            f.close()        
            c4d.CopyStringToClipboard("KEEEYAH!")
            gui.MessageDialog(".json file exported")
#---------------------------------



class Scene_Command(c4d.plugins.MessageData):
    def CoreMessage(self, id, bc):
        if id == c4d.MSG_DOCUMENTINFO:
            "DOC INFO"

        return True

#=================================
# __main__
#=================================
if __name__ == "__main__":
    bmp = bitmaps.BaseBitmap()
    dir, file = os.path.split(__file__)
    bitmapfile = os.path.join(dir, "res", "icon.png")
    
    result = bmp.InitWith(bitmapfile)
    
    if not result:
        print "Error loading Icon!"
    
    okyn = plugins.RegisterObjectPlugin( 
        id=PLUGIN_ID,
        str="Scene_Control",
        info=c4d.OBJECT_GENERATOR,
        g=Scene_Control,
        description="Scene_Control",
        icon=bmp
    )    
    print "BJS_Scene_Control Initialized", okyn
   
    #plugins.RegisterMessagePlugin(id=1054528, str="", info=0, dat=Scene_Command())
    
    
#---------------------------------