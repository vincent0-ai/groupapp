from livekit import api
from livekit import rtc
try:
    from flask import current_app
except Exception:
    current_app = None
from typing import Any
import asyncio
import threading
import concurrent.futures
import types

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
        # Defer creating the LiveKitAPI client until we have a running loop.
        # Try to create it now; if this fails due to no running event loop,
        # start a background loop thread and create the client there.
        self._loop = None
        self._loop_thread = None
        self.lkapi = None

        if hasattr(api, 'LiveKitAPI'):
            try:
                # Attempt to instantiate client (may require a running loop due to aiohttp)
                self.lkapi = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
            except RuntimeError as e:
                # Likely: "no running event loop" from aiohttp.ClientSession
                # Start a background event loop and create the client there.
                self._start_background_loop()
                fut = asyncio.run_coroutine_threadsafe(self._create_client_coro(), self._loop)
                self.lkapi = fut.result(timeout=10)
        else:
            import types
            self.lkapi = types.SimpleNamespace(room=types.SimpleNamespace())

    def _start_background_loop(self):
        if self._loop and self._loop.is_running():
            return
        self._loop = asyncio.new_event_loop()

        def _run_loop(loop: asyncio.AbstractEventLoop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self._loop_thread = threading.Thread(target=_run_loop, args=(self._loop,), daemon=True)
        self._loop_thread.start()

    async def _create_client_coro(self):
        # Run inside the running loop so aiohttp will find the loop
        return api.LiveKitAPI(self.url, self.api_key, self.api_secret)

    def _run_coro(self, coro):
        """Run coroutine and return result; use background loop if available."""
        if self._loop and self._loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return fut.result()
        else:
            # Fallback to running in current thread
            try:
                return asyncio.run(coro)
            except Exception:
                # As a last resort, run synchronously if possible
                raise

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
            # Ensure client exists
            if self.lkapi is None:
                if not hasattr(api, 'LiveKitAPI'):
                    raise RuntimeError('LiveKit SDK not available')
                # create client in background loop if necessary
                try:
                    self.lkapi = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
                except RuntimeError:
                    self._start_background_loop()
                    fut = asyncio.run_coroutine_threadsafe(self._create_client_coro(), self._loop)
                    self.lkapi = fut.result(timeout=10)

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

    def list_participants(self, room_name: str):
        """Sync helper to list participants; runs underlying coroutine on appropriate loop."""
        if not self.lkapi:
            if hasattr(api, 'LiveKitAPI'):
                try:
                    self.lkapi = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
                except RuntimeError:
                    self._start_background_loop()
                    fut = asyncio.run_coroutine_threadsafe(self._create_client_coro(), self._loop)
                    self.lkapi = fut.result(timeout=10)
            else:
                return []

        coro = self.lkapi.room.list_participants(room=room_name)
        return self._run_coro(coro)

    def delete_room(self, room_name: str):
        """Sync helper to delete a room (runs coroutine on background loop)."""
        if not self.lkapi:
            if hasattr(api, 'LiveKitAPI'):
                try:
                    self.lkapi = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
                except RuntimeError:
                    self._start_background_loop()
                    fut = asyncio.run_coroutine_threadsafe(self._create_client_coro(), self._loop)
                    self.lkapi = fut.result(timeout=10)
            else:
                return False, 'SDK not available'

        coro = self.lkapi.room.delete_room(room=room_name)
        return self._run_coro(coro)


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
                # Some LiveKit SDK versions do not accept `room_join` as a kwarg
                try:
                    return api.VideoGrant(
                        room_join=self.room_join,
                        room=self.room,
                        can_publish=self.can_publish,
                        can_publish_data=self.can_publish_data,
                        can_subscribe=self.can_subscribe,
                    )
                except TypeError:
                    # Retry without `room_join` which some versions don't accept
                    return api.VideoGrant(
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
        # Return a simple object with attributes to satisfy older/newer SDK expectations
        return types.SimpleNamespace(
            room_join=self.room_join,
            room=self.room,
            can_publish=self.can_publish,
            can_publish_data=self.can_publish_data,
            can_subscribe=self.can_subscribe,
        )

def get_livekit_service():
    """Factory function to get a LiveKitService instance."""
    return LiveKitService()
