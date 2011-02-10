import sys
import time
import uuid
import traceback
import threading
import base64
from collections import defaultdict

from .terrainsync import TerrainSync

from b2rexpkg.siminfo import GridInfo
from b2rexpkg import IMMEDIATE, ERROR

from .tools.threadpool import ThreadPool, NoResultsPending

from .importer import Importer
from .exporter import Exporter
from .tools.terraindecoder import TerrainDecoder

class RexDrawType:
    Prim = 0
    Mesh = 1

class AssetType:
    OgreMesh = 43
    OgreSkeleton = 44
    OgreMaterial = 45
    OgreParticles = 47
    FlashAnimation = 49
    GAvatar = 46


import bpy

ZERO_UUID_STR = '00000000-0000-0000-0000-000000000000'

if sys.version_info[0] == 3:
        import urllib.request as urllib2
else:
        import urllib2


eventlet_present = False
try:
    import eventlet
    try:
        from b2rexpkg import simrt
        eventlet_present = True
    except:
        traceback.print_exc()
except:
    from b2rexpkg import threadrt as simrt
    eventlet_present = True

import logging
logger = logging.getLogger('b2rex.baseapp')

class BaseApplication(Importer, Exporter):
    def __init__(self, title="RealXtend"):
        self.command_queue = []
        self.wanted_workers = 1
        self.second_start = time.time()
        self.second_budget = 0
        self.pool = ThreadPool(1)
        self.rawselected = set()
        self.agent_id = ""
        self.loglevel = "standard"
        self.agent_access = ""
        self.rt_support = eventlet_present
        self.stats = [0,0,0,0,0,0,0,0,0,0,0,0,0]
        self.status = "b2rex started"
        self.selected = {}
        self.sim_selection = set()
        self.connected = False
        self.positions = {}
        self.rotations = {}
        self.scales = {}
        self.rt_on = False
        self.simrt = None
        self.screen = self
        self.gridinfo = GridInfo()
        self.buttons = {}
        self.settings_visible = False
        self._requested_urls = []
        self.initializeCommands()
        Importer.__init__(self, self.gridinfo)
        Exporter.__init__(self, self.gridinfo)

    def registerCommand(self, cmd, callback):
        self._cmd_matrix[cmd] = callback

    def initializeCommands(self):
        self._cmd_matrix = {}
        self.registerCommand('pos', self.processPosCommand)
        self.registerCommand('rot', self.processRotCommand)
        self.registerCommand('scale', self.processScaleCommand)
        self.registerCommand('delete', self.processDeleteCommand)
        self.registerCommand('msg', self.processMsgCommand)
        self.registerCommand('RexPrimData', self.processRexPrimDataCommand)
        self.registerCommand('LayerData', self.processLayerData)
        self.registerCommand('ObjectProperties', self.processObjectPropertiesCommand)
        self.registerCommand('connected', self.processConnectedCommand)
        self.registerCommand('meshcreated', self.processMeshCreated)
        self.registerCommand('capabilities', self.processCapabilities)
        # internal
        self.registerCommand('mesharrived', self.processMeshArrived)
        self.registerCommand('materialarrived', self.processMaterialArrived)

    def processLayerData(self, layerType, b64data):
        data = base64.urlsafe_b64decode(b64data.encode('ascii'))
        terrpackets = TerrainDecoder.decode(data)
        for header, layer in terrpackets:
            self.terrain.apply_patch(layer, header.x, header.y)

    def processConnectedCommand(self, agent_id, agent_access):
        self.agent_id = agent_id
        self.agent_access = agent_access

    def default_error_db(self, request, error):
        logger.error("error downloading "+str(request)+": "+str(error))
        #traceback.print_tb(error[2])

    def addDownload(self, http_url, cb, cb_pars=(), error_cb=None, main=None):
        if http_url in self._requested_urls:
            return False
        self._requested_urls.append(http_url)
        if not error_cb:
            _error_cb = self.default_error_db
        else:
            def _error_cb(request, result):
                error_cb(result)
        def _cb(request, result):
            cb(result, *cb_pars)
        if not main:
            main = self.doDownload
        self.pool.addRequest(main, [[http_url, cb_pars]], _cb, _error_cb)
        return True

    def doDownload(self, pars):
        http_url, pars = pars
        req = urllib2.urlopen(http_url)
        return req.read()

    def addStatus(self, text, priority=0):
        pass

    def initGui(self, title):
        pass

    def connect(self, base_url, username="", password=""):
        """
        Connect to an opensim instance
        """
        self.sim.connect(base_url+'/xml-rpc.php')
        firstname, lastname = username.split()
        coninfo = self.sim.login(firstname, lastname, password)
        self._sim_port = coninfo['sim_port']
        self._sim_ip = coninfo['sim_ip']
        self._sim_url = 'http://'+str(self._sim_ip)+':'+str(self._sim_port)
        logger.info("reconnect to " + self._sim_url)
        self.gridinfo.connect('http://'+str(self._sim_ip)+':'+str(9000), username, password)
        self.sim.connect(self._sim_url)

    def onConnectAction(self):
        """
        Connect Action
        """
        self.terrain = TerrainSync(self, self.exportSettings.terrainLOD)
        base_url = self.exportSettings.server_url
        self.addStatus("Connecting to " + base_url, IMMEDIATE)
        self.connect(base_url, self.exportSettings.username,
                     self.exportSettings.password)
        self.region_uuid = ''
        self.regionLayout = None
        try:
            self.regions = self.gridinfo.getRegions()
            self.griddata = self.gridinfo.getGridInfo()
        except:
            self.addStatus("Error: couldnt connect to " + base_url, ERROR)
            traceback.print_exc()
            return
        # create the regions panel
        self.addRegionsPanel(self.regions, self.griddata)
        if eventlet_present:
            self.addRtCheckBox()
        else:
            logger.warning("no support for real time communications")

        self.connected = True
        self.addStatus("Connected to " + self.griddata['gridnick'])

    def addRtCheckBox(self):
        pass

    def onToggleRt(self, context=None):
        if context:
            self.exportSettings = context.scene.b2rex_props
        if self.rt_on:
            self.simrt.addCmd(["quit"])
            self.rt_on = False
            self.simrt = None
        else:
            firstline = 'Blender '+ self.getBlenderVersion()
            self.simrt = simrt.run_thread(context, self.exportSettings.server_url,
                                          self.exportSettings.username,
                                          self.exportSettings.password,
                                          firstline)
            self.simrt.addCmd(["throttle", self.exportSettings.kbytesPerSecond*1024])
            if not context:
                Blender.Window.QAdd(Blender.Window.GetAreaID(),Blender.Draw.REDRAW,0,1)
            self.rt_on = True

    def processCommand(self, cmd, *args):
        self.stats[0] += 1
        if cmd in self._cmd_matrix:
            self._cmd_matrix[cmd](*args)

    def processCapabilities(self, caps):
        self.caps = caps

    def processMeshCreated(self, obj_uuid, mesh_uuid, new_obj_uuid, asset_id):
        foundobject = False
        foundmesh = False
        for obj in self.getSelected():
            if obj.type == 'MESH' and obj.opensim.uuid == obj_uuid:
                foundobject = obj
            if obj.type == 'MESH' and obj.data.opensim.uuid == mesh_uuid:
                foundmesh = obj.data

        if not foundmesh:
            foundmesh = self.find_with_uuid(mesh_uuid,
                                              bpy.data.meshes, "meshes")
        if not foundobject:
            foundobject = self.find_with_uuid(obj_uuid,
                                              bpy.data.objects, "objects")
        if foundobject:
            foundobject.opensim.uuid = new_obj_uuid
        else:
            logger.warning("Could not find object for meshcreated")
        if foundmesh:
            foundmesh.opensim.uuid = asset_id
        else:
            logger.warning("Could not find mesh for meshcreated")

    def processDeleteCommand(self, objId):
        obj = self.findWithUUID(objId)
        if obj:
            obj.opensim.uuid = ""
            self.queueRedraw()

    def processRexPrimDataCommand(self, objId, pars):
        self.stats[3] += 1
        meshId = pars["RexMeshUUID"]
        obj = self.findWithUUID(objId)
        if obj or not meshId:
            if obj:
                logger.warning(("Object already created", obj, meshId, objId))
            # XXX we dont update mesh for the moment
            return
        mesh = self.find_with_uuid(meshId, bpy.data.meshes, "meshes")
        if mesh:
            self.createObjectWithMesh(mesh, objId, meshId)
            self.queueRedraw()
        else:
            materials = []
            if "Materials" in pars:
                materials = pars["Materials"]
                for index, matId, asset_type in materials:
                    if not matId == ZERO_UUID_STR and asset_type == AssetType.OgreMaterial:
                        mat_url = self.caps["GetTexture"] + "?texture_id=" + matId
                        self.addDownload(mat_url, self.materialArrived, (objId,
                                                                         meshId,
                                                                         matId,
                                                                         asset_type,
                                                                         index))
                    else:
                        logger.warning("unhandled material of type " + str(asset_type))
            if meshId and not meshId == ZERO_UUID_STR:
                asset_type = pars["drawType"]
                if asset_type == RexDrawType.Mesh:
                    mesh_url = self.caps["GetTexture"] + "?texture_id=" + meshId
                    if not self.addDownload(mesh_url,
                                     self.meshArrived, 
                                     (objId, meshId),
                                            main=self.doMeshDownloadTranscode):
                        self.add_mesh_callback(meshId,
                                               self.createObjectWithMesh,
                                               objId,
                                               meshId)
                else:
                    logger.warning("unhandled rexdata of type " + str(asset_type))

    def processObjectPropertiesCommand(self, objId, pars):
        obj = self.find_with_uuid(str(objId), bpy.data.objects, "objects")
        if obj:
            self.applyObjectProperties(obj, pars)
        self.stats[5] += 1

    def applyObjectProperties(self, obj, pars):
        pass

    def materialArrived(self, data, objId, meshId, matId, assetType, matIdx):
        self.command_queue.append(["materialarrived", data, objId, meshId,
                                      matId, assetType, matIdx])

    def processMaterialArrived(self, data, objId, meshId, matId, assetType, matIdx):
        if assetType == AssetType.OgreMaterial:
            self.parse_material(matId, {"name":matId, "data":data}, meshId,
                                matIdx)

    def meshArrived(self, mesh, objId, meshId):
        self.command_queue.append(["mesharrived", mesh, objId, meshId])

    def processMeshArrived(self, mesh, objId, meshId):
        self.stats[4] += 1
        obj = self.findWithUUID(objId)
        if obj:
            return
        new_mesh = self.create_mesh_fromomesh(meshId, "opensim", mesh)
        if new_mesh:
            self.createObjectWithMesh(new_mesh, str(objId), meshId)
            self.trigger_mesh_callbacks(meshId, new_mesh)
        else:
            print("No new mesh with processMeshArrived")

    def createObjectWithMesh(self, new_mesh, objId, meshId):
        obj = self.getcreate_object(objId, "opensim", new_mesh)
        if objId in self.positions:
            pos = self.positions[objId]
            self.apply_position(obj, pos, raw=True)
        if objId in self.rotations:
            rot = self.rotations[objId]
            self.apply_rotation(obj, rot, raw=True)
        if objId in self.scales:
            scale = self.scales[objId]
            self.apply_scale(obj, scale)
        self.set_uuid(obj, objId)
        self.set_uuid(new_mesh, meshId)
        scene = self.get_current_scene()
        if not obj.name in scene.objects:
            scene.objects.link(obj)
            new_mesh.update()


    def doRtUpload(self, context):
        selected = bpy.context.selected_objects
        if selected:
            # just the first for now
            selected = selected[0]
            if not selected.opensim.uuid:
                self.doRtObjectUpload(context, selected)
                return

    def doDelete(self):
        selected = self.getSelected()
        if selected:
            for obj in selected:
                if obj.opensim.uuid:
                    self.simrt.addCmd(['delete', obj.opensim.uuid])

    def sendObjectClone(self, obj):
        obj_name = obj.name
        mesh = obj.data
        if not obj.opensim.uuid:
            obj.opensim.uuid = str(uuid.uuid4())
        obj_uuid = obj.opensim.uuid
        mesh_name = mesh.name
        mesh_uuid = mesh.opensim.uuid
        pos, rot, scale = self.getObjectProperties(obj)
        
        self.simrt.addCmd(['clone', obj_name, obj_uuid, mesh_name, mesh_uuid,
                           self.unapply_position(pos),
                           self.unapply_rotation(rot), list(scale)])

    def sendObjectUpload(self, obj, mesh, data):
        b64data = base64.urlsafe_b64encode(data).decode('ascii')
        obj_name = obj.name
        obj_uuid = obj.opensim.uuid
        mesh_name = mesh.name
        mesh_uuid = mesh.opensim.uuid
        pos, rot, scale = self.getObjectProperties(obj)
        
        self.simrt.addCmd(['create', obj_name, obj_uuid, mesh_name, mesh_uuid,
                           self.unapply_position(pos),
                           self.unapply_rotation(rot), list(scale), b64data])

    def doRtObjectUpload(self, context, obj):
        mesh = obj.data
        has_mesh_uuid = mesh.opensim.uuid
        if has_mesh_uuid:
            self.sendObjectClone(obj)
            return
        def finish_upload(data):
            self.sendObjectUpload(obj, mesh, data)
        # export mesh
        self.doAsyncExportMesh(context, obj, finish_upload)
        # upload prim
        # self.sendObjectUpload(selected, mesh, data)
        # send new prim

    def processMsgCommand(self, username, message):
        self.addStatus("message from "+username+": "+message)

    def findWithUUID(self, objId):
        obj = self.find_with_uuid(str(objId), bpy.data.objects, "objects")
        return obj

    def processPosCommand(self, objId, pos, rot=None):
        obj = self.findWithUUID(objId)
        if obj:
            self._processPosCommand(obj, objId, pos)
            if rot:
                self._processRotCommand(obj, objId, rot)
        else:
            self.positions[str(objId)] = self._apply_position(pos)
            if rot:
                self.rotations[str(objId)] = self._apply_rotation(rot)

    def processScaleCommand(self, objId, scale):
        obj = self.findWithUUID(objId)
        if obj:
            self._processScaleCommand(obj, objId, scale)
        else:
            self.scales[str(objId)] = scale

    def processRotCommand(self, objId, rot):
        obj = self.findWithUUID(objId)
        if obj:
            self._processRotCommand(obj, objId, rot)
        else:
            self.rotations[str(objId)] = self._apply_rotation(rot)
            
    def processUpdate(self, obj):
        obj_uuid = self.get_uuid(obj)
        if obj_uuid:
            pos, rot, scale = self.getObjectProperties(obj)
            pos = list(pos)
            rot = list(rot)
            scale = list(scale)
            if not obj_uuid in self.rotations or not rot == self.rotations[obj_uuid]:
                self.stats[1] += 1
                self.simrt.apply_position(obj_uuid,  self.unapply_position(pos), self.unapply_rotation(rot))
                self.positions[obj_uuid] = pos
                self.rotations[obj_uuid] = rot
            elif not obj_uuid in self.positions or not pos == self.positions[obj_uuid]:
                self.stats[1] += 1
                self.simrt.apply_position(obj_uuid, self.unapply_position(pos))
                self.positions[obj_uuid] = pos
            if not obj_uuid in self.scales or not scale == self.scales[obj_uuid]:
                self.stats[1] += 1
                self.simrt.apply_scale(obj_uuid, scale)
                self.scales[obj_uuid] = scale
            return obj_uuid


    def checkPool(self):
        # check thread pool size
        if self.wanted_workers != self.exportSettings.pool_workers:
            current_workers = self.wanted_workers
            wanted_workers = self.exportSettings.pool_workers
            if current_workers < wanted_workers:
                self.pool.createWorkers(wanted_workers-current_workers)
            else:
                self.pool.dismissWorkers(current_workers-wanted_workers)
            self.wanted_workers = self.exportSettings.pool_workers

    def processUpdates(self):
        try:
            self.pool.poll()
        except NoResultsPending:
            pass

        # check consistency
        self.checkUuidConsistency(set(self.getSelected()))

        # per second checks
        if time.time() - self.second_start > 1:
            self.checkPool()
            self.second_budget = 0
            self.second_start = time.time()

        # process command queue
        self.processCommandQueue()

    def processCommandQueue(self):
        cmds = self.command_queue + self.simrt.getQueue()
        budget = float(self.exportSettings.rt_budget)/1000.0
        second_budget = float(self.exportSettings.rt_sec_budget)/1000.0
        self.command_queue = []
        currbudget = 0
        processed = 0
        self.stats[8] += 1
        starttime = time.time()
        if cmds:
            self.stats[2] += 1
            for cmd in cmds:
                currbudget = time.time()-starttime
                if currbudget < budget and self.second_budget+currbudget < second_budget or cmd[0] == 'pos':
                    self.processCommand(*cmd)
                    processed += 1
                else:
                    self.command_queue.append(cmd)
        self.second_budget += currbudget
        self.stats[5] = len(self.command_queue)
        self.stats[6] = (currbudget)*1000 # processed
        self.stats[7] = threading.activeCount()-1

        # redraw if we have commands left
        if len(self.command_queue):
            self.queueRedraw()

    def checkUuidConsistency(self, selected):
        # look for duplicates
        if self.rawselected == selected:
            return
        oldselected = self.selected
        newselected = {}
        isobjcopy = True
        for obj in selected:
            obj_uuid = obj.opensim.uuid
            if obj.type == 'MESH' and obj_uuid:
                mesh_uuid = obj.data.opensim.uuid
                if obj.opensim.uuid in oldselected and not oldselected[obj_uuid] == obj.as_pointer():
                    # copy or clone
                    if obj.data.opensim.uuid in oldselected and not oldselected[mesh_uuid] == obj.data.as_pointer():
                        # copy
                        ismeshcopy = True
                        obj.data.opensim.uuid = ""
                    else:
                        # clone
                        pass
                    obj.opensim.uuid = ""
                else:
                    newselected[obj_uuid] = obj.as_pointer()
                    newselected[mesh_uuid] = obj.data.as_pointer()
        self.selected = newselected
        self.rawselected = selected

    def processView(self):
        self.stats[9] += 1

        selected = set(self.getSelected())
        all_selected = set()
        # look for changes in objects
        for obj in selected:
            obj_id = self.get_uuid(obj)
            if obj_id in self.selected and obj.as_pointer() == self.selected[obj_id]:
                self.processUpdate(obj)
                all_selected.add(obj_id)
        # update selection
        if not all_selected == self.sim_selection:
            self.simrt.addCmd(["select"]+list(all_selected))
            self.sim_selection = all_selected

    def go(self):
        """
        Start the ogre interface system
        """
        self.screen.activate()

    def addRegionsPanel(self, regions, griddata):
        pass

    def queueRedraw(self, pars=None):
        pass



