# 🪝 Webhook Setup Guide

## Setting up Real-time Download Status Updates

CuePlex now supports **real-time updates** from Radarr and Sonarr via webhooks, with background polling as fallback.

### 📡 **How It Works**

1. **Webhooks (Primary)**: Radarr/Sonarr send instant updates when downloads start/finish
2. **Background Jobs (Fallback)**: Polls every 5 minutes for any missed updates
3. **Plex Sync**: Marks downloaded items as "Available" when found in Plex

### 🔧 **Radarr Webhook Setup**

1. **Open Radarr** → Settings → Connect
2. **Add Connection** → Webhook
3. **Configure:**
   ```
   Name: CuePlex
   On Grab: ✅ (Download starts)
   On Download: ✅ (Download completes) 
   On Rename: ✅ (Optional)
   On Movie Added: ✅ (Optional)
   
   URL: http://your-cueplex-url/webhooks/radarr
   Method: POST
   Username: (leave empty)
   Password: (leave empty)
   ```

### 📺 **Sonarr Webhook Setup**

1. **Open Sonarr** → Settings → Connect  
2. **Add Connection** → Webhook
3. **Configure:**
   ```
   Name: CuePlex
   On Grab: ✅ (Download starts)
   On Download: ✅ (Episode downloads)
   On Rename: ✅ (Optional)
   On Series Added: ✅ (Optional)
   
   URL: http://your-cueplex-url/webhooks/sonarr
   Method: POST
   Username: (leave empty) 
   Password: (leave empty)
   ```

### 🧪 **Testing Webhooks**

1. **Test endpoint**: `GET /webhooks/test`
2. **Manual trigger**: Admin → Check Download Status
3. **Monitor logs** for webhook events

### 📊 **Status Flow**

```
Request → Approved → Sent to Service → Downloading → Downloaded → Available
   ↑         ↑           ↑              ↑           ↑         ↑
 User    Admin      Auto/Manual    Webhook     Webhook   Plex Sync
```

### 🔄 **Fallback System**

If webhooks fail:
- Background job checks status every 5 minutes
- Manual admin trigger available
- Plex sync handles final "Available" status

### 🚨 **Troubleshooting**

**Webhooks not working?**
- Check Radarr/Sonarr logs for webhook errors
- Verify URL is accessible from Radarr/Sonarr
- Check CuePlex logs for webhook events

**Status not updating?**
- Manual trigger: Admin → Check Download Status  
- Check background job logs (every 5 minutes)
- Verify Radarr/Sonarr IDs are set on requests

**Still stuck?**
- Check service configuration in Admin → Services
- Test individual service connections
- Review request status progression in Admin → Requests