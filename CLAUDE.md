# Stout Requests - Architecture & Development Guidelines

## 📋 Project Overview
Stout Requests is a web application for managing media requests with Plex integration. Users can request movies and TV shows, which admins can approve and automatically add to Plex via Radarr/Sonarr.

## 🏗️ Core Architecture Decision: Hybrid HTMX + API

### Current Approach (Approved)
**Option 3: Responsive Web App with Content Negotiation**

We use a **hybrid approach** that serves both web and potential mobile clients:

1. **Primary Focus**: Responsive HTMX web application
2. **Future-Proof**: Content negotiation for mobile API support
3. **Single Codebase**: One set of endpoints serves both use cases

### Content Negotiation Pattern
```python
@router.post("/endpoint")
async def endpoint_handler(request: Request, ...):
    # Perform business logic
    result = do_work()
    
    # Content negotiation based on client type
    if request.headers.get("HX-Request"):
        # HTMX web client - return HTML fragments
        return HTMLResponse('<div hx-get="..." ...></div>')
    else:
        # API client (mobile, etc.) - return JSON
        return {"success": True, "data": result}
```

### Why This Approach?
- ✅ **Web-first**: HTMX provides excellent UX with minimal JavaScript
- ✅ **Mobile-ready**: JSON APIs available for future native apps
- ✅ **Single source of truth**: One endpoint, two response formats
- ✅ **Performance**: HTMX is faster than SPA for most use cases
- ✅ **Maintainability**: Less complex than separate API + frontend

## 🎯 Development Priorities

### Phase 1: Responsive Web (Current)
- [x] Fix HTMX response issues (JSON appearing on page)
- [x] Implement content negotiation pattern
- [ ] Optimize mobile responsive design
- [ ] Add PWA capabilities (offline, installable)

### Phase 2: API Enhancement (Future)
- [ ] Comprehensive API documentation
- [ ] Mobile app authentication flow
- [ ] Push notifications for mobile
- [ ] Native mobile app development

## 🔧 Technical Standards

### 🚀 **CRITICAL PERFORMANCE PRINCIPLES** 
**⚠️ These are fundamental rules that MUST be followed in all future development:**

#### **Background Processing First**
- **Heavy tasks MUST be background jobs** - Never block the UI with slow operations
- **API calls to external services** → Use immediate integration with proper error handling (don't fail the request if service is down)
- **Database-heavy operations** → Background processing  
- **File processing/uploads** → Background processing
- **Email sending** → Background processing
- **KEEP IT SIMPLE** - Avoid complex background queuing when immediate + error handling works better

#### **Async Everywhere Possible**
- **Use `async/await`** for all I/O operations (database, API calls, file operations)
- **FastAPI endpoints** should be `async def` when doing any I/O
- **Database sessions** should use async patterns where possible
- **External API calls** must be async

#### **HTMX Over JavaScript**
- **Live updates** → Use HTMX `hx-trigger`, `hx-swap-oob`, `hx-target` 
- **Form submissions** → HTMX forms, not JavaScript fetch
- **Dynamic content** → HTMX partials and components
- **Only use JavaScript** when HTMX cannot achieve the desired behavior
- **Speed is the priority** - HTMX + fast endpoints beats JavaScript + slow endpoints

#### **Endpoint Optimization Rules**
- **Request creation** → Instant database write, background service integration
- **Approval/rejection** → Instant status update, background service integration  
- **Status checks** → Background jobs with HTMX polling for updates
- **Never combine** user-facing actions with slow external API calls

### HTMX Best Practices
- **Always return HTML** for `HX-Request` headers
- **Use HTMX triggers** for auto-refresh: `hx-trigger="load delay:5s"`
- **Target specific elements**: `hx-target="#users-list"`
- **Auto-dismiss notifications**: `hx-get="/admin/clear-feedback"`
- **Minimal JavaScript**: Let HTMX handle DOM updates
- **Fast endpoints only**: Never call slow services from HTMX forms

### API Response Standards
For non-HTMX requests, return consistent JSON:
```json
{
  "success": true,
  "message": "Operation completed",
  "data": { ... },
  "errors": null
}
```

### Database Patterns
- **Always set updated_at**: Use `datetime.utcnow()` on modifications
- **Filter NULL timestamps**: `.where(Model.updated_at.isnot(None))`
- **Use proper foreign keys**: Maintain referential integrity
- **Async database operations**: Use async sessions for I/O heavy operations

## 🐛 Known Issues & Solutions

### Issue: "Last Sync: Never"
**Cause**: NULL `updated_at` values in database
**Solution**: Filter out NULL values in queries, backfill existing data

### Issue: JSON Responses on Web
**Cause**: Endpoints returning JSON to HTMX requests
**Solution**: Content negotiation based on `HX-Request` header

### Issue: No Auto-Refresh
**Cause**: Missing HTMX triggers for content updates
**Solution**: Include hidden refresh triggers in success responses

## 📱 Mobile Strategy

### Current Status
- **Web app works on mobile browsers** (responsive design)
- **APIs ready for native development** (JSON responses)
- **PWA potential** (service worker, manifest needed)

### Future Mobile App Features
When native mobile development begins:
- Use existing JSON API endpoints
- Implement push notifications
- Offline request queuing
- Native media player integration

## 🔒 Security Considerations
- **Authentication**: JWT tokens in cookies + headers
- **Authorization**: Role-based access (admin/user)
- **Input validation**: Pydantic models for API requests
- **SQL injection prevention**: SQLModel/SQLAlchemy ORM

## 🧪 Testing Strategy
- **Unit tests**: Core business logic
- **Integration tests**: API endpoints (both HTMX and JSON)
- **E2E tests**: Critical user flows
- **Mobile testing**: Responsive design validation

---

## 📝 Development Notes for Future Sessions

### Key Files
- `/app/api/admin.py` - Admin endpoints with content negotiation
- `/app/templates/admin_dashboard.html` - Main admin interface
- `/app/services/plex_sync_service.py` - Library synchronization
- `/app/templates/base.html` - Global HTMX configuration

### Remember When Working On:
1. **New endpoints**: Always implement content negotiation
2. **HTMX responses**: Return HTML fragments, not JSON
3. **Database updates**: Set proper timestamps
4. **Mobile considerations**: Keep JSON APIs functional
5. **Auto-refresh**: Include HTMX triggers for dynamic updates

### Current Tech Stack
- **Backend**: FastAPI + SQLModel + PostgreSQL
- **Frontend**: HTMX + Tailwind CSS
- **Media Integration**: Plex API + Radarr + Sonarr + TMDB
- **Authentication**: JWT + Plex OAuth

## 🎨 UI/UX Design Standards

### Consistent Poster/Media Card Styling
**IMPORTANT**: All movie and TV show posters throughout the app MUST use the same styling pattern for consistency.

#### Standard Media Card Class Structure:
```html
<div class="movie-card-horizontal group flex-shrink-0 relative bg-white rounded-lg shadow-sm overflow-hidden hover:shadow-xl transition-all duration-300 hover:scale-105">
```

#### Standard Poster Image:
```html
<img src="{{poster_url}}" alt="{{title}}" class="w-full h-72 object-cover">
```

#### Standard Hover Overlay:
```html
<div class="absolute inset-0 bg-gradient-to-t from-black/90 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300">
```

#### Standard Status Badges:
- **In Plex**: `bg-green-600/90 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium`
- **Media Type**: `bg-gray-900/75 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium`
- **Rating**: With yellow star icon and `bg-black/75 backdrop-blur-sm` background

#### Standard Rating Display:
```html
<div class="flex items-center bg-black/75 backdrop-blur-sm px-2 py-1 rounded text-white">
    <svg class="w-3 h-3 text-yellow-400 mr-1" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path>
    </svg>
    <span class="text-xs font-medium">{{rating}}</span>
</div>
```

#### Apply This Pattern To:
- ✅ **Discover page**: Horizontal scroll (category_horizontal.html)
- ✅ **Media detail page**: Horizontal scroll for Similar & Recommended sections
- ✅ **Person detail page**: Grid layout for Known For section (more space available)
- 🔮 **Future pages**: Choose layout based on available space and content volume

#### Layout Decisions:
- **Horizontal Scroll**: Use for discover sections, media recommendations (limited space, browsing)
- **Grid Layout**: Use for person filmography, search results (ample space, comprehensive viewing)

#### Key Design Principles:
1. **Consistency**: Same hover effects, dimensions, and styling across all pages
2. **Accessibility**: Proper alt text, keyboard navigation, screen reader support
3. **Performance**: Optimized images, efficient CSS transitions
4. **Mobile-first**: Responsive design that works on all screen sizes
5. **Status clarity**: Clear visual indicators for Plex availability and request status
6. **Visual Hierarchy**: Use background colors, cards, and sections to break up content
7. **Content Separation**: Avoid large white spaces by creating distinct sections

#### Enhanced Media Detail Page Design:
- **Background Layers**: Alternating `bg-gray-50` and `bg-white` sections
- **Card-based Layout**: White cards with `rounded-xl shadow-lg` for content sections
- **Iconographic Headers**: Colored SVG icons with section titles
- **Separated Content**: Cast, Crew, Details, Similar, and Recommended as distinct sections
- **Crew Section**: Shows key crew members (Director, Producer, etc.) with clickable person links
- **Grid-based Details**: Technical information in responsive card grid layout

This document should be updated as the architecture evolves.