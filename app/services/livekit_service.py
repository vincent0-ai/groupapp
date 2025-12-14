from livekit import api, rtc
from flask import current_app

class LiveKitService:
    """
    Service for interacting with the LiveKit API.
    Provides methods for creating access tokens and managing rooms/participants.
    """
    def __init__(self, api_key=None, api_secret=None, url=None):
        self.api_key = api_key or current_app.config['LIVEKIT_API_KEY']
        self.api_secret = api_secret or current_app.config['LIVEKIT_API_SECRET']
        self.url = url or current_app.config['LIVEKIT_URL']
        
        if not self.api_key or not self.api_secret:
            raise ValueError("LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set.")
            
        self.lkapi = api.LiveKitAPI(self.url, self.api_key, self.api_secret)

    def create_access_token(self, user_id: str, user_name: str, room_name: str, permissions: api.VideoGrant) -> str:
        """
        Create a LiveKit access token for a user.
        """
        token = api.AccessToken(self.api_key, self.api_secret).with_identity(user_id).with_name(user_name).with_grants(permissions)
        
        return token.to_jwt()

    async def update_participant_permission(self, room_name: str, identity: str, can_publish: bool, can_publish_data: bool):
        """
        Update a participant's permissions in a room.
        """
        try:
            permissions = api.VideoGrant(
                can_publish=can_publish,
                can_publish_data=can_publish_data
            )
            await self.lkapi.room.update_participant(
                room=room_name,
                identity=identity,
                permission=permissions
            )
            return True, None
        except rtc.RpcError as e:
            return False, str(e)

    async def remove_participant(self, room_name: str, identity: str):
        """
        Remove a participant from a room.
        """
        try:
            await self.lkapi.room.remove_participant(room=room_name, identity=identity)
            return True, None
        except rtc.RpcError as e:
            return False, str(e)
            
    async def close_room(self, room_name: str):
        """
        End a room session for all participants.
        """
        try:
            await self.lkapi.room.delete_room(room=room_name)
            return True, None
        except rtc.RpcError as e:
            return False, str(e)

def get_livekit_service():
    """Factory function to get a LiveKitService instance."""
    return LiveKitService()
