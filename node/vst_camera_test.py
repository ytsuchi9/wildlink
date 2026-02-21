class VST_Camera:
    def __init__(self, role, params, mqtt_client):
        self.role = role
        self.params = params
        print(f"✅ [VST_Camera] {self.role} 起動完了 (Res: {self.params.get('val_res')})")