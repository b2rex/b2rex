"""
 Object tools panel.
"""

import bpy

col_enum_list = [("None", "None", ""), ("Transfer", "Transfer", "")]
mask_enum = {"Transfer" : 1 << 13,"Modify" : 1 << 14,"Copy" : 1 << 15,"Move" : 1 << 19,"Damage" : 1 << 20}


class ObjectPropertiesPanel(bpy.types.Panel):
    bl_label = "OpenSim" #baseapp.title
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_idname = "b2rex.panel.object"

    def draw_permissions_box(self, obj):
 
        if not hasattr(obj.opensim, 'EveryoneMask'):
            return
        layout = self.layout
        box = layout.box()
        row = box.row()
        expand = obj.opensim.everyonemask_expand
        if expand:
            row.prop(obj.opensim, 'everyonemask_expand', icon="TRIA_DOWN", text='Everyone Permissions', emboss=False)
            for perm, mask in mask_enum.items():
                row = box.row() 
                if getattr(obj.opensim, 'EveryoneMask') & mask: 
                    row.operator("b2rex.setmaskoff", text=perm, icon='LAYER_ACTIVE', emboss=False).mask = mask
                else:
                    row.operator("b2rex.setmaskon", text=perm, icon='LAYER_USED', emboss=False).mask = mask
        else:
            row.prop(obj.opensim, 'everyonemask_expand', icon="TRIA_RIGHT", text='Everyone Permissions', emboss=False)

    def draw(self, context):
        layout = self.layout
        props = context.scene.b2rex_props
        session = bpy.b2rex_session

        box = layout.box()
        for obj in context.selected_objects:
            self.draw_permissions_box(obj)
            if obj.opensim.uuid:
                box.label(text="obj: %s"%(obj.opensim.uuid))
                if obj.type == 'MESH':
                    box.label(text="  mesh: %s"%(obj.data.opensim.uuid))

                box.operator('b2rex.delete', text='Delete from simulator')
            else:
                box.operator('b2rex.exportupload', text='Upload to Sim')


