"""
 GameModule: Functionality related to starting up or running in game engine
 mode.
"""
from .base import SyncModule

import bpy
import os
import mathutils

def processControls():
    bpy.b2rex_session.Game.processControls()

def processCommands():
    bpy.b2rex_session.Game.processCommands()

class GameModule(SyncModule):
    def has_game_uuid(self, obj):
        """
        Returns true if the object has the uuid game property.
        """
        for prop in obj.game.properties:
            if prop.name == 'uuid':
                return True

    def import_object(self, obname):
        opath = "//cube.blend\\Object\\" + obname
        s = os.sep
        dpath = bpy.utils.script_paths()[0] + \
            '%saddons%sb2rexpkg%sdata%sblend%scube.blend\\Object\\' % (s, s, s, s, s)

        # DEBUG
        #print('import_object: ' + opath)

        bpy.ops.wm.link_append(
                filepath=opath,
                filename=obname,
                directory=dpath,
                filemode=1,
                link=False,
                autoselect=True,
                active_layer=True,
                instance_groups=True,
                relative_path=True)
                
       # for ob in bpy.context.selected_objects:
       #     ob.location = bpy.context.scene.cursor_location

    def processControls(self):
        from bge import logic as G
        from bge import render as R
        from bge import events

        sensitivity = 1.0    # mouse sensitivity
        owner = G.getCurrentController().owner
        camera = owner.children[0]

        simrt = bpy.b2rex_session.simrt
        session = bpy.b2rex_session

        if "oldX" not in owner:
            G.mouse.position = (0.5,0.5)
            owner["oldX"] = 0.0
            owner["oldY"] = 0.0
            owner["minX"] = 10.0
            owner["minY"] = 10.0

        else:
            
            # clamp camera to above surface
            #if owner.position[2] < 0:
            #    owner.position[2] = 0
                
            x = 0.5 - G.mouse.position[0]
            y = 0.5 - G.mouse.position[1]
            
            if abs(x) > abs(owner["minX"]) and abs(y) > abs(owner["minY"]):
            
                x *= sensitivity
                y *= sensitivity
                
                # Smooth movement
                #owner['oldX'] = (owner['oldX']*0.5 + x*0.5)
                #owner['oldY'] = (owner['oldY']*0.5 + y*0.5)
                #x = owner['oldX']
                #y = owner['oldY']
                 
                # set the values
                owner.applyRotation([0, 0, x], False)
                camera.applyRotation([y, 0, 0], True)
                
                _rotmat = owner.worldOrientation
                print(_rotmat)
                _roteul = _rotmat.to_euler()
                _roteul[0] = 0
                _roteul[1] = 0
                rot = session.unapply_rotation(_roteul)
            #    print(rot)
                simrt.BodyRotation(rot)
            
            else:
                owner["minX"] = x
                owner["minY"] = y
                
            # Center mouse in game window
           

            G.mouse.position = (0.5,0.5)
            
            # keyboard control
            keyboard = G.keyboard.events
            if keyboard[events.WKEY]:
                print("WALKT")
                simrt.Walk(True)
            elif keyboard[events.SKEY]:
                simrt.WalkBackwards(True)
            elif keyboard[events.AKEY]:
                simrt.BodyRotation([1, 0, 0, 1])
            elif keyboard[events.DKEY]:
                simrt.BodyRotation([1, 1, 0, 1])
            else:
                simrt.Stop()

    def processCommands(self):
        from bge import logic as G
        from bge import render as R
        from bge import events

        speed = 0.2    # walk speed
        sensitivity = 1.0    # mouse sensitivity

        owner = G.getCurrentController().owner

        simrt = bpy.b2rex_session.simrt
        session = bpy.b2rex_session

        if not "avatar" in bpy.data.objects:
            self.import_object("avatar")
            

        avatar = bpy.data.objects["avatar"]

        commands = simrt.getQueue()

        print('processCommands', len(commands), avatar)
        for command in commands:
            print(' *', command)
            if command[0] == "pos":
                self.processPosition(owner, *command[1:])

    def processPosition(self, owner, objid, pos, rot=None):
        session = bpy.b2rex_session
        if objid == session.agent_id:
            print(pos, owner.get("uuid"))
            owner.worldPosition = session._apply_position(pos)
            if rot:
               b_q = mathutils.Quaternion((rot[3], rot[0], rot[1], rot[2]))
               owner.worldOrientation = b_q


    def ensure_game_uuid(self, context, obj):
        """
        Ensure the uuid is set as a game object property.
        """
        if obj.opensim.uuid:
            if not self.has_game_uuid(obj):
                obj.select = True
                context.scene.objects.active = obj
                bpy.ops.object.game_property_new()
                # need to change type and then get the property otherwise
                # it will stay in the wrong class
                obj.game.properties[-1].type = 'STRING'
                prop = obj.game.properties[-1]
                prop.name = 'uuid'
                prop.value = obj.opensim.uuid
                obj.select = False
            if obj.opensim.uuid == self._parent.agent_id:
                self.prepare_avatar(context, obj)

    def prepare_avatar(self, context, obj):
        if not len(obj.game.sensors):
            bpy.ops.logic.sensor_add( type='ALWAYS'  )
            sensor = obj.game.sensors[-1]
            sensor.use_pulse_true_level = True
        if not len(obj.game.controllers):
            for name in ['processCommands', 'processControls']:
                bpy.ops.logic.controller_add( type='PYTHON'  )
                controller = obj.game.controllers[-1]
                controller.mode = 'MODULE'
                controller.module = 'b2rexpkg.editsync.handlers.game.' + name
                controller.link(sensor=obj.game.sensors[-1])

    def prepare_object(self, context, obj):
        """
        Prepare the given object for running inside the
        game engine.
        """
        self.ensure_game_uuid(context, obj)

    def start_game(self, context):
        """
        Start blender game engine, previously setting up game
        properties for opensim.
        """
        selected = list(context.selected_objects)
        for obj in selected:
            obj.select = False
        for obj in bpy.data.objects:
            self.prepare_object(context, obj)
        for obj in selected:
            obj.select = True
        bpy.ops.view3d.game_start()
