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
from datetime import datetime

class LiveKitService:
    """
    Service for interacting with the LiveKit API.
    Provides methods for creating access tokens and managing rooms/participants.
    """
    def __init__(self):
        self.api_key = None
        self.api_secret = None
        self.url = None
        self._loop = None
        self._loop_thread = None
        self.lkapi = None

    def init_app(self, app):
        self.api_key = app.config.get('LIVEKIT_API_KEY')
        self.api_secret = app.config.get('LIVEKIT_API_SECRET')
        self.url = app.config.get('LIVEKIT_URL')

        if not self.api_key or not self.api_secret:
            raise ValueError("LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set in config.")

        if hasattr(api, 'LiveKitAPI'):
            try:
                self.lkapi = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
            except RuntimeError:
                self._start_background_loop()
                fut = asyncio.run_coroutine_threadsafe(self._create_client_coro(), self._loop)
                self.lkapi = fut.result(timeout=10)
        else:
            self.lkapi = types.SimpleNamespace(room=types.SimpleNamespace())

    def _start_background_loop(self):
        # Only create a new loop if we don't have one or if our thread isn't alive
        if self._loop and self._loop.is_running() and self._loop_thread and self._loop_thread.is_alive():
            return
        
        # Create a new event loop for background use
        self._loop = asyncio.new_event_loop()

        def _run_loop(loop: asyncio.AbstractEventLoop):
            asyncio.set_event_loop(loop)
            try:
                loop.run_forever()
            except RuntimeError:
                pass  # Ignore if loop is already running

        self._loop_thread = threading.Thread(target=_run_loop, args=(self._loop,), daemon=True)
        self._loop_thread.start()
        # Give the thread a moment to start
        import time
        time.sleep(0.01)

    async def _create_client_coro(self):
        # Run inside the running loop so aiohttp will find the loop
        return api.LiveKitAPI(self.url, self.api_key, self.api_secret)

    def _run_coro(self, coro):
        """Run coroutine and return result; use background loop if available."""
        # First check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop is not None:
            # Already in an event loop - use background loop or nest if possible
            if self._loop and self._loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
                return fut.result(timeout=10)
            else:
                # Start a background loop if we don't have one
                self._start_background_loop()
                fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
                return fut.result(timeout=10)
        elif self._loop and self._loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return fut.result(timeout=10)
        else:
            # No running loop - safe to use asyncio.run
            try:
                return asyncio.run(coro)
            except RuntimeError:
                # Last resort: start background loop
                self._start_background_loop()
                fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
                return fut.result(timeout=10)

    def create_access_token(self, user_id: str, user_name: str, room_name: str, permissions: Any) -> str:
        """
        Create a LiveKit access token for a user.
        """
        native_permissions = permissions.to_api() if hasattr(permissions, 'to_api') else permissions

        # Helper to convert dicts into objects with attribute access (recursively)
        def _to_obj(d):
            if isinstance(d, dict):
                return types.SimpleNamespace(**{k: _to_obj(v) for k, v in d.items()})
            return d

        try:
            token_builder = api.AccessToken(self.api_key, self.api_secret).with_identity(user_id).with_name(user_name)

            # Normalize permission fields (accept both snake_case and camelCase)
            def _get_attr(obj, *names, default=None):
                for n in names:
                    if hasattr(obj, n):
                        return getattr(obj, n)
                return default

            if native_permissions:
                p = native_permissions
                # If it's a dict, convert to SimpleNamespace for attribute access
                if isinstance(p, dict):
                    p = _to_obj(p)

                room = _get_attr(p, 'room', 'room')
                room_join = _get_attr(p, 'room_join', 'roomJoin', default=True)
                can_publish = _get_attr(p, 'can_publish', 'canPublish', default=False)
                can_publish_data = _get_attr(p, 'can_publish_data', 'canPublishData', default=False)
                can_subscribe = _get_attr(p, 'can_subscribe', 'canSubscribe', default=True)
                hidden = _get_attr(p, 'hidden', 'hidden', default=False)

                video_kwargs_snake = dict(room_join=room_join, room=room, can_publish=can_publish, can_publish_data=can_publish_data, can_subscribe=can_subscribe, hidden=hidden)
                video_kwargs_camel = dict(roomJoin=room_join, room=room, canPublish=can_publish, canPublishData=can_publish_data, canSubscribe=can_subscribe, hidden=hidden)

                prepared = None
                # Try constructing an SDK VideoGrant/VideoGrants in multiple ways
                if hasattr(api, 'VideoGrants'):
                    try:
                        prepared = api.VideoGrants(**video_kwargs_snake)
                        print('Using api.VideoGrants with snake_case')
                    except Exception:
                        try:
                            prepared = api.VideoGrants(**video_kwargs_camel)
                            print('Using api.VideoGrants with camelCase')
                        except Exception as e:
                            print('api.VideoGrants not accepted:', e)

                if prepared is None and hasattr(api, 'VideoGrant'):
                    try:
                        prepared = api.VideoGrant(**video_kwargs_snake)
                        print('Using api.VideoGrant with snake_case')
                    except Exception:
                        try:
                            prepared = api.VideoGrant(**video_kwargs_camel)
                            print('Using api.VideoGrant with camelCase')
                        except Exception as e:
                            print('api.VideoGrant not accepted:', e)

                # Fallback: create an object with a `video` attribute
                if prepared is None:
                    grant_inner = types.SimpleNamespace(**video_kwargs_snake)
                    prepared = types.SimpleNamespace(video=grant_inner)

                try:
                    token_builder = token_builder.with_grants(prepared)
                except Exception as e:
                    print('with_grants failed:', e)
                    raise

            token_str = token_builder.to_jwt()
            # Try to decode token; if it's not a JWT (e.g., test dummy), return as-is
            try:
                import jwt as _pyjwt
                decoded = _pyjwt.decode(token_str, options={"verify_signature": False})
            except Exception:
                return token_str

            # If token has no video grant or room info, fall back to creating a manual token
            if not decoded.get('video') or not decoded.get('video', {}).get('room'):
                try:
                    now = int(datetime.utcnow().timestamp())
                    ttl = 3600
                    payload = {
                        'iss': self.api_key,
                        'sub': user_id,
                        'name': user_name,
                        'nbf': now,
                        'exp': now + ttl,
                        'video': {
                            'room': room_name,
                            'roomJoin': True,
                            'canPublish': getattr(native_permissions, 'can_publish', True) if not isinstance(native_permissions, dict) else (native_permissions.get('can_publish') if native_permissions.get('can_publish') is not None else True),
                            'canPublishData': getattr(native_permissions, 'can_publish_data', True) if not isinstance(native_permissions, dict) else (native_permissions.get('can_publish_data') if native_permissions.get('can_publish_data') is not None else True),
                            'canSubscribe': getattr(native_permissions, 'can_subscribe', True) if not isinstance(native_permissions, dict) else (native_permissions.get('can_subscribe') if native_permissions.get('can_subscribe') is not None else True),
                            'hidden': getattr(native_permissions, 'hidden', False) if not isinstance(native_permissions, dict) else (native_permissions.get('hidden') if native_permissions.get('hidden') is not None else False),
                        },
                        'metadata': ''
                    }
                    manual = _pyjwt.encode(payload, self.api_secret, algorithm='HS256')
                    print('Generated manual JWT with video grant as fallback')
                    return manual
                except Exception as e:
                    print('Failed to create manual JWT fallback:', e)
                    return token_str

            return token_str
        except Exception:
            # Fall back to issuing a token without explicit grants to avoid SDK incompatibilities
            tb = None
            try:
                import traceback
                tb = traceback.format_exc()
                print('Access token generation failed, falling back to token without grants:', tb)
            except Exception:
                pass
            token_builder = api.AccessToken(self.api_key, self.api_secret).with_identity(user_id).with_name(user_name)
            return token_builder.to_jwt()

    async def update_participant_permission(self, room_name: str, identity: str, can_publish: bool, can_publish_data: bool):
        """
        Update a participant's permissions in a room.
        """
        print(f"[LiveKitService] update_participant_permission called room={room_name} identity={identity} can_publish={can_publish} can_publish_data={can_publish_data}")
        try:
            # Use compatibility wrapper so code works across LiveKit SDK versions
            permissions = VideoGrants(
                can_publish=can_publish,
                can_publish_data=can_publish_data
            ).to_api()
            try:
                print(f"[LiveKitService] prepared permissions: {repr(permissions)}")
            except Exception:
                print("[LiveKitService] prepared permissions (repr failed)")
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
            try:
                print(f"[LiveKitService] calling LiveKit API update_participant room={room_name} identity={identity}")
                await self.lkapi.room.update_participant(
                    room=room_name,
                    identity=identity,
                    permission=permissions
                )
                print(f"[LiveKitService] LiveKit update_participant succeeded for identity={identity} room={room_name}")
                return True, None
            except Exception as e:
                print(f"[LiveKitService] LiveKit update_participant RPC error for identity={identity} room={room_name}: {e}")
                try:
                    import traceback
                    traceback.print_exc()
                except Exception:
                    pass
                return False, str(e)
        except rtc.RpcError as e:
            print(f"[LiveKitService] caught rtc.RpcError: {e}")
            return False, str(e)
        except Exception as e:
            print(f"[LiveKitService] unexpected error in update_participant_permission: {e}")
            try:
                import traceback
                traceback.print_exc()
            except Exception:
                pass
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

        # The SDK's list_participants signature varies between versions.
        # Newer SDK uses ListParticipantsRequest object
        coro = None
        try:
            # Try newer SDK pattern with api.ListParticipantsRequest
            if hasattr(api, 'ListParticipantsRequest'):
                req = api.ListParticipantsRequest(room=room_name)
                coro = self.lkapi.room.list_participants(req)
            else:
                # Try older patterns
                coro = self.lkapi.room.list_participants(room=room_name)
        except TypeError:
            try:
                coro = self.lkapi.room.list_participants(room_name)
            except TypeError:
                # Fall back to calling without args
                coro = self.lkapi.room.list_participants()
        
        if coro is None:
            return []
            
        try:
            result = self._run_coro(coro)
            # Result might be a ListParticipantsResponse object
            if hasattr(result, 'participants'):
                return result.participants
            return result if result else []
        except Exception as e:
            print(f"list_participants error: {e}")
            return []
        finally:
            # Try to close any underlying aiohttp session to avoid 'Unclosed client session' warnings
            try:
                self.maybe_close_session()
            except Exception:
                pass

    def maybe_close_session(self):
        """Attempt to close underlying aiohttp ClientSession if present on the LiveKit API client."""
        if not self.lkapi:
            return
        sess = getattr(self.lkapi, 'session', None)
        if sess is None:
            # Some versions keep session on ._session or similar
            sess = getattr(self.lkapi, '_session', None)
        if sess is None:
            return
        try:
            # Attempt to call close() and handle both coroutine and synchronous variants
            if hasattr(sess, 'close'):
                try:
                    ret = sess.close()
                    # If calling close() returned a coroutine, ensure it runs to completion
                    if asyncio.iscoroutine(ret):
                        if self._loop and self._loop.is_running():
                            fut = asyncio.run_coroutine_threadsafe(ret, self._loop)
                            fut.result(timeout=5)
                        else:
                            asyncio.run(ret)
                    else:
                        # close executed synchronously (no coroutine returned)
                        pass
                except TypeError:
                    # In some environments close may need to be called to get a coroutine
                    try:
                        coro = sess.close()
                        if asyncio.iscoroutine(coro):
                            if self._loop and self._loop.is_running():
                                fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
                                fut.result(timeout=5)
                            else:
                                asyncio.run(coro)
                    except Exception:
                        pass
        except Exception:
            pass

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
    `api.ParticipantPermission`) and otherwise falls back to a dict-like
    object. Newer code may pass a `hidden` flag to hide a participant
    (for example, so a non-speaking participant does not appear to others).
    """
    def __init__(self, *, room_join: bool = True, room: str | None = None, can_publish: bool = True, can_publish_data: bool = False, can_subscribe: bool = True, hidden: bool = False):
        self.room_join = room_join
        self.room = room
        self.can_publish = can_publish
        self.can_publish_data = can_publish_data
        self.can_subscribe = can_subscribe
        self.hidden = hidden

    def to_api(self):
        # Prefer api.VideoGrants (newer SDK) then api.VideoGrant (older naming)
        # Try both snake_case and camelCase kwarg names to be robust across versions.
        if hasattr(api, 'VideoGrants'):
            try:
                try:
                    return api.VideoGrants(
                        room_join=self.room_join,
                        room=self.room,
                        can_publish=self.can_publish,
                        can_publish_data=self.can_publish_data,
                        can_subscribe=self.can_subscribe,
                        hidden=self.hidden,
                    )
                except TypeError:
                    return api.VideoGrants(
                        room=self.room,
                        roomJoin=self.room_join,
                        canPublish=self.can_publish,
                        canPublishData=self.can_publish_data,
                        canSubscribe=self.can_subscribe,
                        hidden=self.hidden,
                    )
            except Exception:
                pass

        if hasattr(api, 'VideoGrant'):
            try:
                try:
                    return api.VideoGrant(
                        room_join=self.room_join,
                        room=self.room,
                        can_publish=self.can_publish,
                        can_publish_data=self.can_publish_data,
                        can_subscribe=self.can_subscribe,
                        hidden=self.hidden,
                    )
                except TypeError:
                    return api.VideoGrant(
                        room=self.room,
                        roomJoin=self.room_join,
                        canPublish=self.can_publish,
                        canPublishData=self.can_publish_data,
                        canSubscribe=self.can_subscribe,
                        hidden=self.hidden,
                    )
            except Exception:
                pass

        # Fallback to ParticipantPermission if present
        if hasattr(api, 'ParticipantPermission'):
            try:
                # Some SDKs accept a `hidden` flag here too; try to provide it.
                try:
                    return api.ParticipantPermission(
                        can_publish=self.can_publish,
                        can_publish_data=self.can_publish_data,
                        hidden=self.hidden,
                    )
                except TypeError:
                    # Fallback if the parameter name or support differs
                    return api.ParticipantPermission(
                        can_publish=self.can_publish,
                        can_publish_data=self.can_publish_data,
                    )
            except Exception:
                pass

        # Final fallback: include `hidden` attribute so callers that read the
        # prepared object can observe the intent even when SDK integration is
        # not available.
        return types.SimpleNamespace(
            room_join=self.room_join,
            room=self.room,
            can_publish=self.can_publish,
            can_publish_data=self.can_publish_data,
            can_subscribe=self.can_subscribe,
            hidden=self.hidden,
        )

def get_livekit_service():
    """Factory function to get a LiveKitService instance."""
    return LiveKitService()
