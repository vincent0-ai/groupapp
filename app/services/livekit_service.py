from livekit import api
from livekit import rtc
try:
    from flask import current_app
except Exception:
    current_app = None
from typing import Any

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
            
        # Create LiveKitAPI client if available in the SDK; otherwise use a minimal stub
        if hasattr(api, 'LiveKitAPI'):
            self.lkapi = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
        else:
            import types
            self.lkapi = types.SimpleNamespace(room=types.SimpleNamespace())

    def create_access_token(self, user_id: str, user_name: str, room_name: str, permissions: Any) -> str:
        """
        Create a LiveKit access token for a user.
        """
        native_permissions = permissions.to_api() if hasattr(permissions, 'to_api') else permissions
        token = api.AccessToken(self.api_key, self.api_secret).with_identity(user_id).with_name(user_name).with_grants(native_permissions)
        
        return token.to_jwt()

    async def update_participant_permission(self, room_name: str, identity: str, can_publish: bool, can_publish_data: bool):
        """
        Update a participant's permissions in a room.
        """
        try:
            # Use compatibility wrapper so code works across LiveKit SDK versions
            permissions = VideoGrants(
                can_publish=can_publish,
                can_publish_data=can_publish_data
            ).to_api()
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


class VideoGrants:
    """Compatibility wrapper for LiveKit grant/permission objects.

    Builds an SDK-native grant when available (`api.VideoGrant` or
    `api.ParticipantPermission`) and otherwise falls back to a dict.
    """
    def __init__(self, *, room_join: bool = False, room: str | None = None, can_publish: bool = False, can_publish_data: bool = False, can_subscribe: bool = True):
        self.room_join = room_join
        self.room = room
        self.can_publish = can_publish
        self.can_publish_data = can_publish_data
        self.can_subscribe = can_subscribe

    def to_api(self):
        # Prefer api.VideoGrant when available
        if hasattr(api, 'VideoGrant'):
            try:
                return api.VideoGrant(
                    room_join=self.room_join,
                    room=self.room,
                    can_publish=self.can_publish,
                    can_publish_data=self.can_publish_data,
                    can_subscribe=self.can_subscribe,
                )
            except Exception:
                pass

        # Fallback to ParticipantPermission if present
        if hasattr(api, 'ParticipantPermission'):
            try:
                return api.ParticipantPermission(
                    can_publish=self.can_publish,
                    can_publish_data=self.can_publish_data,
                )
            except Exception:
                pass

        # Final fallback: plain dict
        return {
            'room_join': self.room_join,
            'room': self.room,
            'can_publish': self.can_publish,
            'can_publish_data': self.can_publish_data,
            'can_subscribe': self.can_subscribe,
        }

def get_livekit_service():
    """Factory function to get a LiveKitService instance."""
    return LiveKitService()
