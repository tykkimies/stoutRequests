import asyncio
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlmodel import Session, select, delete
from plexapi.server import PlexServer

from ..core.database import get_session, engine
from ..models.plex_library_item import PlexLibraryItem
from ..models.plex_tv_item import PlexTVItem
from ..models.media_request import MediaRequest, RequestStatus
from ..services.plex_service import PlexService
from ..services.settings_service import SettingsService


class PlexSyncService:
    def __init__(self, session: Session = None):
        if session is None:
            self.session = Session(engine)
            self._owns_session = True
        else:
            self.session = session
            self._owns_session = False
    
    def safe_print(self, message: str):
        """Safely print message with proper encoding handling"""
        try:
            # Remove or replace problematic characters
            safe_msg = str(message).encode('ascii', errors='ignore').decode('ascii')
            print(safe_msg if safe_msg.strip() else "[Non-ASCII characters removed]")
        except Exception:
            print("[Encoding error in message]")
    
    def __del__(self):
        if hasattr(self, '_owns_session') and self._owns_session and hasattr(self, 'session'):
            self.session.close()
    
    async def sync_library(self) -> Dict[str, int]:
        """
        Sync Plex library to local database.
        Returns dictionary with sync statistics.
        """
        try:
            print("🔄 Starting Plex library sync...")
            
            # Clean up any existing duplicates first
            await self._cleanup_duplicates()
            
            # Get Plex configuration
            config = SettingsService.get_plex_config(self.session)
            if not config.get('url') or not config.get('token'):
                print("❌ Plex not configured, skipping sync")
                return {'error': 'Plex not configured'}
            
            # Ensure URL and token are properly encoded for HTTP headers
            clean_url = str(config['url']).encode('ascii', errors='ignore').decode('ascii').strip()
            clean_token = str(config['token']).encode('ascii', errors='ignore').decode('ascii').strip()
            
            plex = PlexServer(clean_url, clean_token)
            self.safe_print(f"🔗 Connected to Plex server: {plex.friendlyName}")
            
            stats = {
                'movies_processed': 0,
                'shows_processed': 0,
                'items_added': 0,
                'items_updated': 0,
                'items_removed': 0,
                'requests_updated': 0
            }
            
            # Get all current library items to track what should be removed
            existing_items = {}
            existing_statement = select(PlexLibraryItem)
            for item in self.session.exec(existing_statement):
                existing_items[item.plex_key] = item
            
            # Get sync preferences
            settings = SettingsService.get_settings(self.session)
            selected_libraries = settings.get_sync_library_preferences()
            
            self.safe_print(f"🎯 Library sync preferences: {selected_libraries}")
            if not selected_libraries:
                self.safe_print("📋 No specific library preferences set - will sync all libraries")
            else:
                self.safe_print(f"📋 Will only sync selected libraries: {', '.join(selected_libraries)}")
            
            # Process all library sections
            available_sections = [f"{s.title} ({s.type})" for s in plex.library.sections() if s.type in ['movie', 'show']]
            self.safe_print(f"🔍 Available Plex sections: {', '.join(available_sections)}")
            
            for section in plex.library.sections():
                if section.type in ['movie', 'show']:
                    # Check if this library should be synced
                    should_sync = settings.should_sync_library(section.title)
                    self.safe_print(f"🔍 Checking {section.title} ({section.type}): should_sync = {should_sync}")
                    
                    if not should_sync:
                        self.safe_print(f"⏭️  Skipping {section.title} ({section.type}) library (not in sync preferences)")
                        continue
                    
                    self.safe_print(f"📚 Processing {section.title} ({section.type}) library...")
                    
                    try:
                        # Get all items in this section
                        all_items = section.all()
                        self.safe_print(f"   Found {len(all_items)} items in {section.title}")
                        
                        for item in all_items:
                            try:
                                plex_key = f"{item.ratingKey}"
                                
                                # Extract TMDB ID from guid
                                tmdb_id = None
                                for guid in getattr(item, 'guids', []):
                                    guid_id = getattr(guid, 'id', '')
                                    if 'tmdb://' in guid_id:
                                        try:
                                            tmdb_id = int(guid_id.split('tmdb://')[1])
                                            break
                                        except (ValueError, IndexError):
                                            continue
                                
                                # If no TMDB ID found, try to match by title/year as fallback
                                if not tmdb_id:
                                    tmdb_id = await self._match_by_title_year(item.title, getattr(item, 'year', None), 'tv')
                                
                                # Skip items we can't match at all
                                if not tmdb_id:
                                    self.safe_print(f"⚠️ Skipping {item.title} - no TMDB ID and no title/year match found")
                                    continue
                                
                                # Determine media type
                                media_type = 'movie' if section.type == 'movie' else 'tv'
                                
                                # For TV shows, also sync seasons and episodes
                                if media_type == 'tv':
                                    await self._sync_tv_show_details(item, tmdb_id)
                                
                                # Check if item exists in our database by plex_key
                                if plex_key in existing_items:
                                    # Update existing item
                                    existing_item = existing_items[plex_key]
                                    existing_item.tmdb_id = tmdb_id
                                    existing_item.title = str(item.title).encode('utf-8', errors='replace').decode('utf-8').strip()
                                    existing_item.media_type = media_type
                                    existing_item.year = getattr(item, 'year', None)
                                    existing_item.rating_key = item.ratingKey
                                    existing_item.library_section_id = section.key
                                    existing_item.added_at = getattr(item, 'addedAt', None)
                                    existing_item.updated_at = datetime.utcnow()
                                    
                                    stats['items_updated'] += 1
                                    # Remove from tracking (so we don't delete it later)
                                    del existing_items[plex_key]
                                else:
                                    # Check if an item with this tmdb_id + media_type already exists
                                    existing_tmdb_item = self.session.exec(
                                        select(PlexLibraryItem).where(
                                            PlexLibraryItem.tmdb_id == tmdb_id,
                                            PlexLibraryItem.media_type == media_type
                                        )
                                    ).first()
                                    
                                    if existing_tmdb_item:
                                        # Update the existing TMDB item with new Plex info (prefer newer data)
                                        self.safe_print(f"🔄 Updating existing TMDB item {tmdb_id} ({media_type}) with new Plex key {plex_key}")
                                        existing_tmdb_item.plex_key = plex_key
                                        existing_tmdb_item.title = str(item.title).encode('utf-8', errors='replace').decode('utf-8').strip()
                                        existing_tmdb_item.year = getattr(item, 'year', None)
                                        existing_tmdb_item.rating_key = item.ratingKey
                                        existing_tmdb_item.library_section_id = section.key
                                        existing_tmdb_item.added_at = getattr(item, 'addedAt', None)
                                        existing_tmdb_item.updated_at = datetime.utcnow()
                                        stats['items_updated'] += 1
                                    else:
                                        # Create new item
                                        new_item = PlexLibraryItem(
                                            plex_key=plex_key,
                                            tmdb_id=tmdb_id,
                                            title=str(item.title).encode('utf-8', errors='replace').decode('utf-8').strip(),
                                            media_type=media_type,
                                            year=getattr(item, 'year', None),
                                            rating_key=item.ratingKey,
                                            library_section_id=section.key,
                                            added_at=getattr(item, 'addedAt', None),
                                            created_at=datetime.utcnow()
                                        )
                                        self.session.add(new_item)
                                        stats['items_added'] += 1
                                
                                # Update stats
                                if media_type == 'movie':
                                    stats['movies_processed'] += 1
                                else:
                                    stats['shows_processed'] += 1
                                    
                            except Exception as item_error:
                                self.safe_print(f"⚠️ Error processing item {getattr(item, 'title', 'Unknown')}: {item_error}")
                                continue
                                
                    except Exception as section_error:
                        self.safe_print(f"❌ Error processing section {section.title}: {section_error}")
                        continue
            
            # Remove items that are no longer in Plex
            for plex_key, item in existing_items.items():
                self.safe_print(f"🗑️ Removing item no longer in Plex: {item.title}")
                self.session.delete(item)
                stats['items_removed'] += 1
            
            # Commit all changes with error handling
            try:
                self.session.commit()
                print(f"💾 Database changes committed")
            except Exception as commit_error:
                print(f"❌ Error committing changes: {commit_error}")
                self.session.rollback()
                # Try to continue with individual commits to salvage what we can
                print("🔄 Attempting individual item commits...")
                individual_stats = await self._commit_items_individually()
                stats.update(individual_stats)
                return stats
            
            # Update request statuses for newly available items
            stats['requests_updated'] = await self._update_request_statuses()
            
            print(f"✅ Plex library sync completed!")
            print(f"   📊 Stats: {stats}")
            
            return stats
            
        except Exception as e:
            print(f"❌ Error during Plex library sync: {e}")
            traceback.print_exc()
            self.session.rollback()
            return {'error': str(e)}
    
    async def _cleanup_duplicates(self):
        """Clean up any duplicate entries based on (tmdb_id, media_type) constraint"""
        try:
            print("🧹 Checking for duplicate entries...")
            
            # Find duplicates using SQL
            from sqlalchemy import text
            duplicate_query = text("""
                SELECT tmdb_id, media_type, COUNT(*) as count
                FROM plex_library_item 
                WHERE tmdb_id IS NOT NULL
                GROUP BY tmdb_id, media_type 
                HAVING COUNT(*) > 1
            """)
            
            duplicates = self.session.exec(duplicate_query).all()
            
            if duplicates:
                print(f"🔍 Found {len(duplicates)} sets of duplicate entries")
                
                for dup in duplicates:
                    tmdb_id, media_type, count = dup
                    print(f"   Cleaning up {count} duplicates for TMDB ID {tmdb_id} ({media_type})")
                    
                    # Get all items with this tmdb_id/media_type, keep the most recent one
                    items = list(self.session.exec(
                        select(PlexLibraryItem).where(
                            PlexLibraryItem.tmdb_id == tmdb_id,
                            PlexLibraryItem.media_type == media_type
                        ).order_by(PlexLibraryItem.updated_at.desc(), PlexLibraryItem.created_at.desc())
                    ))
                    
                    # Keep the first (most recent) item, delete the rest
                    for item_to_delete in items[1:]:
                        print(f"   🗑️ Removing duplicate: {item_to_delete.title} (plex_key: {item_to_delete.plex_key})")
                        self.session.delete(item_to_delete)
                
                # Commit the cleanup
                self.session.commit()
                print(f"✅ Cleaned up duplicates")
            else:
                print("✅ No duplicates found")
                
        except Exception as e:
            print(f"⚠️ Error during duplicate cleanup: {e}")
            self.session.rollback()
    
    async def _sync_tv_show_details(self, show_item, tmdb_id: int):
        """Sync detailed season and episode information for a TV show"""
        try:
            # Clean up existing TV item records for this show
            delete_stmt = delete(PlexTVItem).where(PlexTVItem.show_tmdb_id == tmdb_id)
            self.session.exec(delete_stmt)
            
            # Get all seasons for this show
            for season in show_item.seasons():
                season_number = season.seasonNumber
                
                # Skip season 0 (specials) for now to keep it simple
                if season_number == 0:
                    continue
                
                # Add season-level entry
                season_item = PlexTVItem(
                    show_tmdb_id=tmdb_id,
                    show_title=show_item.title,
                    season_number=season_number,
                    episode_number=None,  # None indicates this is a season-level entry
                    plex_key=f"{season.ratingKey}",
                    library_section_id=show_item.librarySectionID,
                    added_at=getattr(season, 'addedAt', None),
                    created_at=datetime.utcnow()
                )
                self.session.add(season_item)
                
                # Get all episodes in this season
                try:
                    for episode in season.episodes():
                        episode_item = PlexTVItem(
                            show_tmdb_id=tmdb_id,
                            show_title=show_item.title,
                            season_number=season_number,
                            episode_number=episode.episodeNumber,
                            episode_title=episode.title,
                            plex_key=f"{episode.ratingKey}",
                            library_section_id=show_item.librarySectionID,
                            added_at=getattr(episode, 'addedAt', None),
                            created_at=datetime.utcnow()
                        )
                        self.session.add(episode_item)
                except Exception as episode_error:
                    print(f"⚠️ Error syncing episodes for season {season_number} of {show_item.title}: {episode_error}")
                    continue
                    
        except Exception as e:
            print(f"⚠️ Error syncing TV show details for {show_item.title}: {e}")

    async def _commit_items_individually(self) -> Dict[str, int]:
        """
        Fallback method to commit items one by one when bulk commit fails.
        This helps identify and skip problematic items.
        """
        stats = {'items_saved': 0, 'items_failed': 0}
        
        # This is a fallback - in a real implementation you'd need to track
        # which items were being added/updated and commit them individually
        # For now, just return empty stats as the main sync will be retried
        print("⚠️ Individual commit fallback not fully implemented - will retry sync")
        return stats
    
    async def _update_request_statuses(self) -> int:
        """
        Update request statuses for items that are now available in Plex.
        Returns number of requests updated.
        """
        try:
            print("🔄 Updating request statuses...")
            
            # Find pending/approved requests that are now available in Plex
            from sqlalchemy import text
            update_query = text("""
                UPDATE mediarequest 
                SET status = 'AVAILABLE', updated_at = NOW()
                WHERE status IN ('PENDING', 'APPROVED')
                AND EXISTS (
                    SELECT 1 FROM plex_library_item 
                    WHERE plex_library_item.tmdb_id = mediarequest.tmdb_id 
                    AND plex_library_item.media_type::text = mediarequest.media_type::text
                )
            """)
            
            result = self.session.exec(update_query)
            updated_count = result.rowcount if hasattr(result, 'rowcount') else 0
            
            self.session.commit()
            print(f"✅ Updated {updated_count} request statuses to 'available'")
            
            return updated_count
            
        except Exception as e:
            print(f"❌ Error updating request statuses: {e}")
            self.session.rollback()
            return 0
    
    def get_sync_stats(self) -> Dict[str, any]:
        """Get statistics about the current library sync state"""
        try:
            # Count items by type
            movie_count = len(list(self.session.exec(
                select(PlexLibraryItem).where(PlexLibraryItem.media_type == 'movie')
            )))
            
            tv_count = len(list(self.session.exec(
                select(PlexLibraryItem).where(PlexLibraryItem.media_type == 'tv')
            )))
            
            # Get last sync time (most recent updated_at, excluding NULL values)
            latest_item = self.session.exec(
                select(PlexLibraryItem)
                .where(PlexLibraryItem.updated_at.isnot(None))
                .order_by(PlexLibraryItem.updated_at.desc())
            ).first()
            
            last_sync = latest_item.updated_at if latest_item else None
            
            return {
                'total_items': movie_count + tv_count,
                'movies': movie_count,
                'tv_shows': tv_count,
                'last_sync': last_sync.isoformat() if last_sync else None,
                'sync_age_hours': (datetime.utcnow() - last_sync).total_seconds() / 3600 if last_sync else None
            }
            
        except Exception as e:
            self.safe_print(f"Error getting sync stats: {e}")
            return {'error': str(e)}
    
    def debug_show_sync(self, tmdb_id: int) -> Dict[str, any]:
        """Debug method to check why a specific show isn't syncing"""
        try:
            debug_info = {
                'tmdb_id': tmdb_id,
                'found_in_plex': False,
                'found_in_db': False,
                'plex_items': [],
                'db_items': [],
                'plex_connection': None,
                'libraries_checked': []
            }
            
            # Check if it exists in our database
            db_items = list(self.session.exec(
                select(PlexLibraryItem).where(PlexLibraryItem.tmdb_id == tmdb_id)
            ))
            debug_info['db_items'] = [
                {
                    'id': item.id,
                    'title': item.title,
                    'media_type': item.media_type,
                    'plex_key': item.plex_key,
                    'year': item.year,
                    'library_section_id': item.library_section_id
                } for item in db_items
            ]
            debug_info['found_in_db'] = len(db_items) > 0
            
            # Try to connect to Plex and search for this show
            try:
                config = SettingsService.get_plex_config(self.session)
                if not config.get('url') or not config.get('token'):
                    debug_info['plex_connection'] = 'No Plex config found'
                    return debug_info
                
                clean_url = str(config['url']).encode('ascii', errors='ignore').decode('ascii').strip()
                clean_token = str(config['token']).encode('ascii', errors='ignore').decode('ascii').strip()
                plex = PlexServer(clean_url, clean_token)
                debug_info['plex_connection'] = f"Connected to {plex.friendlyName}"
                
                # Check all TV libraries
                for section in plex.library.sections():
                    if section.type == 'show':
                        debug_info['libraries_checked'].append({
                            'name': section.title,
                            'key': section.key,
                            'type': section.type
                        })
                        
                        # Search for shows with this TMDB ID
                        try:
                            search_results = section.search(guid=f'tmdb://{tmdb_id}')
                            if search_results:
                                for show in search_results:
                                    debug_info['plex_items'].append({
                                        'title': show.title,
                                        'year': getattr(show, 'year', None),
                                        'rating_key': show.ratingKey,
                                        'library': section.title,
                                        'guids': [guid.id for guid in getattr(show, 'guids', [])]
                                    })
                                    debug_info['found_in_plex'] = True
                        except Exception as search_error:
                            print(f"Error searching section {section.title}: {search_error}")
                            
                        # Also try manual check of all shows in this library
                        try:
                            print(f"Manually checking all shows in {section.title} for TMDB ID {tmdb_id}...")
                            all_shows = section.all()
                            for show in all_shows:
                                for guid in getattr(show, 'guids', []):
                                    if f'tmdb://{tmdb_id}' in guid.id:
                                        debug_info['plex_items'].append({
                                            'title': show.title,
                                            'year': getattr(show, 'year', None),
                                            'rating_key': show.ratingKey,
                                            'library': section.title,
                                            'guids': [g.id for g in getattr(show, 'guids', [])],
                                            'found_via': 'manual_search'
                                        })
                                        debug_info['found_in_plex'] = True
                                        break
                        except Exception as manual_error:
                            print(f"Error in manual search of {section.title}: {manual_error}")
                            
            except Exception as plex_error:
                debug_info['plex_connection'] = f"Plex connection error: {str(plex_error)}"
            
            return debug_info
            
        except Exception as e:
            return {'error': f"Debug error: {str(e)}"}
    
    def debug_library_guids(self, search_term: str = None) -> Dict[str, any]:
        """Debug method to show all GUIDs in the TV library, optionally filtered by search term"""
        try:
            debug_info = {
                'search_term': search_term,
                'plex_connection': None,
                'tv_shows_found': [],
                'guid_analysis': {
                    'tmdb_shows': 0,
                    'tvdb_shows': 0,
                    'imdb_shows': 0,
                    'other_shows': 0
                }
            }
            
            # Try to connect to Plex
            try:
                config = SettingsService.get_plex_config(self.session)
                if not config.get('url') or not config.get('token'):
                    debug_info['plex_connection'] = 'No Plex config found'
                    return debug_info
                
                clean_url = str(config['url']).encode('ascii', errors='ignore').decode('ascii').strip()
                clean_token = str(config['token']).encode('ascii', errors='ignore').decode('ascii').strip()
                plex = PlexServer(clean_url, clean_token)
                debug_info['plex_connection'] = f"Connected to {plex.friendlyName}"
                
                # Get TV library
                for section in plex.library.sections():
                    if section.type == 'show':
                        print(f"Analyzing TV library: {section.title}")
                        
                        try:
                            all_shows = section.all()
                            print(f"Found {len(all_shows)} shows in library")
                            
                            for show in all_shows:
                                # If search term provided, filter by title
                                if search_term and search_term.lower() not in show.title.lower():
                                    continue
                                    
                                show_info = {
                                    'title': show.title,
                                    'year': getattr(show, 'year', None),
                                    'rating_key': show.ratingKey,
                                    'guids': []
                                }
                                
                                # Get all GUIDs for this show
                                for guid in getattr(show, 'guids', []):
                                    guid_info = {
                                        'id': guid.id,
                                        'type': 'unknown'
                                    }
                                    
                                    # Categorize the GUID
                                    if 'tmdb://' in guid.id:
                                        guid_info['type'] = 'tmdb'
                                        try:
                                            guid_info['extracted_id'] = int(guid.id.split('tmdb://')[1])
                                        except:
                                            pass
                                        debug_info['guid_analysis']['tmdb_shows'] += 1
                                    elif 'tvdb://' in guid.id:
                                        guid_info['type'] = 'tvdb'
                                        try:
                                            guid_info['extracted_id'] = int(guid.id.split('tvdb://')[1])
                                        except:
                                            pass
                                        debug_info['guid_analysis']['tvdb_shows'] += 1
                                    elif 'imdb://' in guid.id:
                                        guid_info['type'] = 'imdb'
                                        guid_info['extracted_id'] = guid.id.split('imdb://')[1]
                                        debug_info['guid_analysis']['imdb_shows'] += 1
                                    else:
                                        debug_info['guid_analysis']['other_shows'] += 1
                                    
                                    show_info['guids'].append(guid_info)
                                
                                debug_info['tv_shows_found'].append(show_info)
                                
                                # Limit results to prevent huge responses
                                if len(debug_info['tv_shows_found']) >= 50:
                                    debug_info['note'] = 'Results limited to first 50 shows'
                                    break
                                    
                        except Exception as library_error:
                            debug_info['library_error'] = str(library_error)
                            
            except Exception as plex_error:
                debug_info['plex_connection'] = f"Plex connection error: {str(plex_error)}"
            
            return debug_info
            
        except Exception as e:
            return {'error': f"Debug error: {str(e)}"}
    
    async def _match_by_title_year(self, title: str, year: int, media_type: str) -> Optional[int]:
        """
        Try to match a Plex item to TMDB by title and year when no GUID is available.
        Returns TMDB ID if found, None otherwise.
        """
        try:
            from ..services.tmdb_service import TMDBService
            tmdb_service = TMDBService(self.session)
            
            # Search TMDB for this title
            search_results = tmdb_service.search_multi(title)
            
            if not search_results.get('results'):
                return None
            
            # Look for exact matches by title and year
            for result in search_results['results']:
                result_media_type = result.get('media_type')
                result_title = result.get('title') or result.get('name')
                result_year = None
                
                # Extract year from release date
                if result.get('release_date'):
                    try:
                        result_year = int(result['release_date'][:4])
                    except:
                        pass
                elif result.get('first_air_date'):
                    try:
                        result_year = int(result['first_air_date'][:4])
                    except:
                        pass
                
                # Check for match
                if (result_media_type == media_type and 
                    result_title and result_title.lower() == title.lower() and
                    result_year == year):
                    
                    print(f"✅ Matched {title} ({year}) to TMDB ID {result['id']} via title/year")
                    return result['id']
            
            # If no exact match, try fuzzy matching (without year requirement)
            for result in search_results['results']:
                result_media_type = result.get('media_type')
                result_title = result.get('title') or result.get('name')
                
                if (result_media_type == media_type and 
                    result_title and result_title.lower() == title.lower()):
                    
                    print(f"🔄 Fuzzy matched {title} to TMDB ID {result['id']} via title only (year mismatch)")
                    return result['id']
            
            print(f"❌ No TMDB match found for {title} ({year})")
            return None
            
        except Exception as e:
            print(f"⚠️ Error matching {title} by title/year: {e}")
            return None
    
    def debug_tv_completion(self, tmdb_id: int) -> Dict[str, any]:
        """Debug method to check TV show completion status"""
        try:
            debug_info = {
                'tmdb_id': tmdb_id,
                'in_plex_library': False,
                'has_detailed_data': False,
                'completion_status': None,
                'plex_tv_items': [],
                'season_summary': {}
            }
            
            # Check if show is in main library
            plex_item = self.session.exec(
                select(PlexLibraryItem).where(
                    PlexLibraryItem.tmdb_id == tmdb_id,
                    PlexLibraryItem.media_type == 'tv'
                )
            ).first()
            
            if plex_item:
                debug_info['in_plex_library'] = True
                debug_info['plex_library_item'] = {
                    'title': plex_item.title,
                    'year': plex_item.year,
                    'plex_key': plex_item.plex_key
                }
            
            # Check detailed TV data
            tv_items = list(self.session.exec(
                select(PlexTVItem).where(PlexTVItem.show_tmdb_id == tmdb_id)
            ))
            
            if tv_items:
                debug_info['has_detailed_data'] = True
                debug_info['plex_tv_items'] = [
                    {
                        'season_number': item.season_number,
                        'episode_number': item.episode_number,
                        'episode_title': item.episode_title,
                        'plex_key': item.plex_key
                    } for item in tv_items
                ]
                
                # Get completion status
                debug_info['completion_status'] = self._check_tv_show_completion(tmdb_id)
                
                # Summarize seasons
                seasons = {}
                for item in tv_items:
                    season_num = item.season_number
                    if season_num not in seasons:
                        seasons[season_num] = {'episodes': 0, 'has_season_entry': False}
                    
                    if item.episode_number is None:
                        seasons[season_num]['has_season_entry'] = True
                    else:
                        seasons[season_num]['episodes'] += 1
                
                debug_info['season_summary'] = seasons
            
            # Compare with TMDB data
            try:
                from ..services.tmdb_service import TMDBService
                tmdb_service = TMDBService(self.session)
                tmdb_details = tmdb_service.get_tv_details(tmdb_id)
                
                debug_info['tmdb_info'] = {
                    'total_seasons': tmdb_details.get('number_of_seasons'),
                    'total_episodes': tmdb_details.get('number_of_episodes'),
                    'status': tmdb_details.get('status'),
                    'last_air_date': tmdb_details.get('last_air_date')
                }
                
            except Exception as tmdb_error:
                debug_info['tmdb_error'] = str(tmdb_error)
            
            return debug_info
            
        except Exception as e:
            return {'error': f"Debug error: {str(e)}"}
    
    def check_items_status(self, tmdb_ids: List[int], media_type: str, skip_tv_completion: bool = False) -> Dict[int, str]:
        """
        Fast lookup of status for multiple TMDB IDs.
        Returns dict mapping tmdb_id -> status ('in_plex', 'partial_plex', 'requested_pending', 'requested_approved', 'available')
        """
        try:
            if not tmdb_ids:
                return {}
            
            status_map = {}
            
            # Check which items are in Plex
            plex_statement = select(PlexLibraryItem).where(
                PlexLibraryItem.tmdb_id.in_(tmdb_ids),
                PlexLibraryItem.media_type == media_type
            )
            plex_items = {item.tmdb_id for item in self.session.exec(plex_statement)}
            # Only show debug for single item checks to reduce noise
            if len(tmdb_ids) == 1:
                print(f"🔍 [PLEX STATUS DEBUG] Checking {len(tmdb_ids)} {media_type} items: {tmdb_ids}")
                print(f"🔍 [PLEX STATUS DEBUG] Found {len(plex_items)} items in Plex: {plex_items}")
            
            # For TV shows, check if they're partial (unless skipped for performance)
            if media_type == 'tv':
                if skip_tv_completion:
                    # Fast mode: Just check if show exists in Plex, skip completion checking
                    for tmdb_id in tmdb_ids:
                        if tmdb_id in plex_items:
                            status_map[tmdb_id] = 'in_plex'  # Assume complete for performance
                        else:
                            status_map[tmdb_id] = 'available'  # Default
                else:
                    # Full mode: Check completion status (expensive)
                    # Check which TV shows have detailed episode data
                    tv_statement = select(PlexTVItem.show_tmdb_id).where(
                        PlexTVItem.show_tmdb_id.in_(tmdb_ids)
                    ).distinct()
                    tv_items_with_details = {item for item in self.session.exec(tv_statement)}
                    
                    # For shows with detailed data, check if they're complete
                    for tmdb_id in tmdb_ids:
                        if tmdb_id in plex_items:
                            if tmdb_id in tv_items_with_details:
                                # Check if this show is complete by getting TMDB details
                                completion_status = self._check_tv_show_completion(tmdb_id)
                                if completion_status['is_complete']:
                                    status_map[tmdb_id] = 'in_plex'
                                else:
                                    status_map[tmdb_id] = 'partial_plex'
                            else:
                                # No detailed data, assume complete for now
                                status_map[tmdb_id] = 'in_plex'
                        else:
                            status_map[tmdb_id] = 'available'  # Default
            else:
                # For movies, simple check
                for tmdb_id in tmdb_ids:
                    if tmdb_id in plex_items:
                        status_map[tmdb_id] = 'in_plex'
                        # Only show debug for single item checks to reduce noise
                        if len(tmdb_ids) == 1:
                            print(f"🔍 [PLEX STATUS DEBUG] Movie {tmdb_id} found in Plex library")
                    else:
                        status_map[tmdb_id] = 'available'  # Default
                        # Only show debug for single item checks to reduce noise
                        if len(tmdb_ids) == 1:
                            print(f"🔍 [PLEX STATUS DEBUG] Movie {tmdb_id} NOT found in Plex library")
            
            # Check which items have been requested
            request_statement = select(MediaRequest).where(
                MediaRequest.tmdb_id.in_(tmdb_ids),
                MediaRequest.media_type == media_type,
                MediaRequest.status.in_([RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.AVAILABLE, RequestStatus.REJECTED])
            )
            
            # Override with request status if exists
            for request in self.session.exec(request_statement):
                if request.status == RequestStatus.AVAILABLE:
                    # AVAILABLE requests mean the item is fully in Plex
                    status_map[request.tmdb_id] = 'in_plex'
                else:
                    # Active requests (PENDING/APPROVED) should show request status
                    # This includes partial shows that have new requests for missing content
                    if status_map.get(request.tmdb_id) != 'in_plex':
                        status_map[request.tmdb_id] = f'requested_{request.status.value.lower()}'
            
            return status_map
            
        except Exception as e:
            print(f"Error checking items status: {e}")
            # Fallback to 'available' for all items
            return {tmdb_id: 'available' for tmdb_id in tmdb_ids}
    
    def get_tv_episode_availability(self, tmdb_id: int) -> Dict[str, any]:
        """
        Get detailed episode availability data for a TV show.
        Returns dict with season-by-season and episode-by-episode availability.
        """
        try:
            from sqlmodel import select
            
            # Get all available episodes from Plex
            episodes_query = select(PlexTVItem).where(
                PlexTVItem.show_tmdb_id == tmdb_id,
                PlexTVItem.episode_number.isnot(None)  # Only episodes, not seasons
            )
            available_episodes = self.session.exec(episodes_query).all()
            
            # Get all available seasons from Plex
            seasons_query = select(PlexTVItem).where(
                PlexTVItem.show_tmdb_id == tmdb_id,
                PlexTVItem.episode_number.is_(None),  # Only seasons, not episodes
                PlexTVItem.season_number > 0  # Exclude specials
            )
            available_seasons = self.session.exec(seasons_query).all()
            
            # Organize data by season
            availability_data = {
                'seasons': {},
                'summary': {
                    'total_available_seasons': len(available_seasons),
                    'total_available_episodes': len(available_episodes),
                    'available_season_numbers': [s.season_number for s in available_seasons]
                }
            }
            
            # Group episodes by season
            for episode in available_episodes:
                season_num = episode.season_number
                if season_num not in availability_data['seasons']:
                    availability_data['seasons'][season_num] = {
                        'season_available': season_num in availability_data['summary']['available_season_numbers'],
                        'episodes': []
                    }
                
                availability_data['seasons'][season_num]['episodes'].append({
                    'episode_number': episode.episode_number,
                    'episode_title': episode.episode_title,
                    'available': True
                })
            
            return availability_data
            
        except Exception as e:
            print(f"❌ Error getting TV episode availability: {e}")
            return {'seasons': {}, 'summary': {}}

    def _check_tv_show_completion(self, tmdb_id: int) -> Dict[str, any]:
        """
        Check if a TV show is complete in Plex by comparing against TMDB data.
        Only considers regular seasons (ignoring specials/season 0).
        """
        try:
            # Get available seasons and episodes from our detailed data
            completion_data = PlexTVItem.get_show_completion_status(self.session, tmdb_id)
            available_seasons = completion_data.get('available_seasons', 0)
            available_episodes = completion_data.get('available_episodes', 0)
            available_season_numbers = completion_data.get('season_numbers', [])
            
            # Get TMDB data for comparison
            try:
                from ..services.tmdb_service import TMDBService
                tmdb_service = TMDBService(self.session)
                tmdb_details = tmdb_service.get_tv_details(tmdb_id)
                
                # Get total regular seasons and episodes from TMDB (excluding specials)
                tmdb_total_seasons = tmdb_details.get('number_of_seasons', 0)
                tmdb_total_episodes = tmdb_details.get('number_of_episodes', 0)
                
                # Get detailed season info and count only AIRED episodes (not future ones)
                tmdb_regular_seasons = 0
                tmdb_aired_episodes = 0
                tmdb_total_episodes = 0
                
                if tmdb_details.get('seasons'):
                    from datetime import datetime
                    today = datetime.now()
                    
                    for season in tmdb_details['seasons']:
                        season_number = season.get('season_number', 0)
                        if season_number > 0:  # Exclude season 0 (specials)
                            tmdb_regular_seasons += 1
                            season_episode_count = season.get('episode_count', 0)
                            tmdb_total_episodes += season_episode_count
                            
                            # Count aired episodes by checking air dates
                            season_aired = 0
                            if 'episodes' in season:
                                for ep in season['episodes']:
                                    ep_air_date = ep.get('air_date')
                                    if ep_air_date:
                                        try:
                                            air_dt = datetime.strptime(ep_air_date, '%Y-%m-%d')
                                            if air_dt <= today:
                                                season_aired += 1
                                        except:
                                            # If we can't parse the date, assume it has aired
                                            season_aired += 1
                                    else:
                                        # No air date info, assume it has aired if within reasonable bounds
                                        season_aired += 1
                            else:
                                # No detailed episode data, use conservative estimate
                                # For ongoing shows, don't assume all episodes have aired
                                show_status = tmdb_details.get('status', '').lower()
                                if show_status in ['returning series', 'in production']:
                                    # For ongoing shows, estimate based on air date patterns
                                    # Use a weekly schedule assumption (1 episode per week)
                                    season_air_date = season.get('air_date')
                                    if season_air_date:
                                        try:
                                            season_start = datetime.strptime(season_air_date, '%Y-%m-%d')
                                            weeks_since_start = (today - season_start).days // 7
                                            # Conservative estimate: min of weeks passed or total episodes
                                            season_aired = min(max(0, weeks_since_start), season_episode_count)
                                        except:
                                            # Fallback to half the episodes for ongoing shows
                                            season_aired = season_episode_count // 2
                                    else:
                                        # No air date, assume half have aired for ongoing shows
                                        season_aired = season_episode_count // 2
                                else:
                                    # For completed shows, assume all episodes have aired
                                    season_aired = season_episode_count
                            
                            tmdb_aired_episodes += season_aired
                
                # Compare our data against AIRED episodes (not total planned)
                # Show is "complete" if we have all aired episodes
                is_complete = (
                    available_episodes >= tmdb_aired_episodes and 
                    available_seasons > 0  # Must have at least one season
                )
                
                return {
                    'is_complete': is_complete,
                    'available_seasons': available_seasons,
                    'available_episodes': available_episodes,
                    'season_numbers': available_season_numbers,
                    'tmdb_regular_seasons': tmdb_regular_seasons,
                    'tmdb_aired_episodes': tmdb_aired_episodes,
                    'tmdb_total_episodes': tmdb_total_episodes,
                    'completion_percentage': (available_episodes / tmdb_aired_episodes * 100) if tmdb_aired_episodes > 0 else 0
                }
                
            except Exception as tmdb_error:
                print(f"Error getting TMDB data for completion check {tmdb_id}: {tmdb_error}")
                # If we can't get TMDB data, consider it partial if we have any episodes
                return {
                    'is_complete': False,  # Default to partial when we can't verify
                    'available_seasons': available_seasons,
                    'available_episodes': available_episodes,
                    'season_numbers': available_season_numbers,
                    'tmdb_error': str(tmdb_error)
                }
            
        except Exception as e:
            print(f"Error checking TV show completion for {tmdb_id}: {e}")
            return {
                'is_complete': False,  # Default to partial on error
                'available_seasons': 0,
                'available_episodes': 0,
                'season_numbers': [],
                'error': str(e)
            }


# Scheduled task function (to be called by background job scheduler)
async def run_plex_sync():
    """Function to be called by scheduler/cron job"""
    try:
        sync_service = PlexSyncService()
        result = await sync_service.sync_library()
        print(f"Scheduled Plex sync completed: {result}")
        return result
    except Exception as e:
        print(f"Error in scheduled Plex sync: {e}")
        return {'error': str(e)}