"""
 OnlineModule: Manages agent online and offline messages from the simulator.
"""
import uuid

from .base import SyncModule

import bpy

LLSDText = 10

class ScriptingModule(SyncModule):
    def register(self, parent):
        """
        Register this module with the editor
        """
        parent.Asset.registerAssetType(LLSDText, self.create_llsd_script)
        return
        parent.registerCommand('OfflineNotification',
                             self.processOfflineNotification)
        parent.registerCommand('OnlineNotification',
                             self.processOnlineNotification)
    def unregister(self, parent):
        """
        Unregister this module from the editor
        """
        return
        parent.unregisterCommand('OfflineNotification')
        parent.unregisterCommand('OnlineNotification')

    def upload(self, name):
        editor = self._parent
        text_obj = bpy.data.texts[name]
        self.upload_text(text_obj)

    def find_text(self, text_uuid):
        editor = self._parent
        return editor.find_with_uuid(text_uuid, bpy.data.texts, 'texts')

    def create_llsd_script(self, assetID, assetType, data):
        editor = self._parent
        text = data.decode('ascii')
        name = 'text'

        for item in editor.Inventory:
            if item['AssetID'] == assetID:
                name = item['Name']

        text_obj = bpy.data.texts.new(name)
        text_obj.write(text)
        text_obj.opensim.uuid = assetID
        

    def upload_text(self, text_obj):
        editor = self._parent
        text_data = ""
        # gather text data
        for line in text_obj.lines:
            text_data += line.body + "\n"
        # initialize object sim state
        name = text_obj.name
        desc = "test script"
        item_id = ""

        # asset uploaded callback
        def upload_finished(old_uuid, new_uuid, tr_uuid):
            text_obj.opensim.uuid = new_uuid
            text_obj.opensim.state = 'OK'
            self.simrt.CreateInventoryItem(tr_uuid,
                                           LLSDText,
                                           LLSDText,
                                           name,
                                           desc)
        def update_finished(old_uuid, new_uuid, tr_uuid):
            text_obj.opensim.uuid = new_uuid
            text_obj.opensim.state = 'OK'
            item = editor.Inventory[item_id]
            # XXX this should happen automatically?
            item['AssetID'] = new_uuid
            self.simrt.UpdateInventoryItem(item_id,
                                           tr_uuid,
                                           LLSDText,
                                           LLSDText,
                                           name,
                                           desc)

        if text_obj.opensim.uuid:
            for item in editor.Inventory:
                if item['AssetID'] == text_obj.opensim.uuid:
                    item_id = item['ItemID']

            cb = update_finished
        else:
            text_obj.opensim.uuid = str(uuid.uuid4())
            cb = upload_finished
        text_obj.opensim.state = 'UPLOADING'
        # start uploading
        editor.Asset.upload(text_obj.opensim.uuid, LLSDText,
                            text_data.encode('ascii'),
                            cb)

