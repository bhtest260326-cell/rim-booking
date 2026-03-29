"""
admin_pro/ui/js_route.py
Route optimization visualization JavaScript for the Admin Pro UI.
"""

JS_ROUTE = """
// ============================================================
// Admin Pro — Route Optimization Visualization
// ============================================================

// ── Route State ─────────────────────────────────────────────
const ROUTE_STATE = {
  currentDate: null,
  routeData: null,
  map: null,
  markers: [],
  polyline: null,
  infoWindow: null,
};

// ── Fetch route data from API ────────────────────────────────
async function fetchRouteData(dateStr) {
  try {
    var data = await apiFetch('/v2/api/route/' + dateStr);
    return data;
  } catch (e) {
    console.error('Failed to fetch route data:', e);
    return null;
  }
}

// ── Open route map modal ─────────────────────────────────────
async function openRouteMap(dateStr) {
  if (!dateStr) {
    dateStr = new Date().toISOString().slice(0, 10);
  }
  ROUTE_STATE.currentDate = dateStr;

  // Show modal
  var modal = document.getElementById('route-map-modal');
  if (!modal) {
    _createRouteModal();
    modal = document.getElementById('route-map-modal');
  }
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  // Show loading state
  var content = document.getElementById('route-map-content');
  if (content) {
    content.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:300px;color:var(--ap-text-muted,#64748b)">Loading route data...</div>';
  }

  // Fetch route data
  var data = await fetchRouteData(dateStr);
  ROUTE_STATE.routeData = data;

  if (!data || !data.stops || data.stops.length === 0) {
    if (content) {
      content.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:300px;color:var(--ap-text-muted,#64748b)">No confirmed jobs for ' + escapeHtml(dateStr) + '</div>';
    }
    _updateRouteSummary(data);
    return;
  }

  _renderRouteContent(data);
}

// ── Create the route modal element ───────────────────────────
function _createRouteModal() {
  var modal = document.createElement('div');
  modal.id = 'route-map-modal';
  modal.className = 'ap-modal-overlay';
  modal.style.display = 'none';
  modal.style.position = 'fixed';
  modal.style.inset = '0';
  modal.style.zIndex = '9999';
  modal.style.background = 'rgba(0,0,0,0.5)';
  modal.style.display = 'none';
  modal.style.alignItems = 'center';
  modal.style.justifyContent = 'center';
  modal.onclick = function(e) {
    if (e.target === modal) closeRouteMap();
  };

  modal.innerHTML = '' +
    '<div style="background:var(--ap-surface,#fff);border-radius:12px;width:95%;max-width:1100px;max-height:90vh;overflow:auto;box-shadow:0 20px 60px rgba(0,0,0,0.3)">' +
      '<div style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--ap-border,#e2e8f0)">' +
        '<div>' +
          '<h3 style="margin:0;font-size:18px;color:var(--ap-text,#1e293b)">Route Map</h3>' +
          '<span id="route-map-date" style="font-size:13px;color:var(--ap-text-muted,#64748b)"></span>' +
        '</div>' +
        '<div style="display:flex;gap:8px;align-items:center">' +
          '<a id="route-gmaps-link" href="#" target="_blank" rel="noopener" class="ap-btn ap-btn-sm ap-btn-ghost" style="text-decoration:none;display:none">Open in Google Maps</a>' +
          '<button onclick="closeRouteMap()" class="ap-btn ap-btn-sm ap-btn-ghost" style="font-size:18px;padding:4px 10px">&times;</button>' +
        '</div>' +
      '</div>' +
      '<div id="route-summary-bar" style="display:flex;gap:20px;padding:12px 20px;background:var(--ap-bg,#f8fafc);border-bottom:1px solid var(--ap-border,#e2e8f0);flex-wrap:wrap">' +
        '<div id="route-stat-stops" class="route-stat"></div>' +
        '<div id="route-stat-travel" class="route-stat"></div>' +
        '<div id="route-stat-distance" class="route-stat"></div>' +
        '<div id="route-stat-times" class="route-stat"></div>' +
      '</div>' +
      '<div id="route-map-content" style="padding:20px;min-height:400px">' +
        '<div style="display:flex;align-items:center;justify-content:center;height:300px;color:var(--ap-text-muted,#64748b)">Loading...</div>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);
}

function closeRouteMap() {
  var modal = document.getElementById('route-map-modal');
  if (modal) {
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }
  // Clean up Google Maps objects
  ROUTE_STATE.markers = [];
  ROUTE_STATE.polyline = null;
  ROUTE_STATE.map = null;
  ROUTE_STATE.infoWindow = null;
}

// ── Render route content ─────────────────────────────────────
function _renderRouteContent(data) {
  var dateLabel = document.getElementById('route-map-date');
  if (dateLabel) dateLabel.textContent = data.date;

  _updateRouteSummary(data);
  _buildGoogleMapsLink(data);

  var content = document.getElementById('route-map-content');
  if (!content) return;

  // Build the content: map container + stop list
  var html = '';

  // Map container
  html += '<div id="route-map-canvas" style="width:100%;height:400px;border-radius:8px;background:var(--ap-bg,#f1f5f9);margin-bottom:16px;position:relative">';
  html += '<div id="route-map-fallback" style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--ap-text-muted,#64748b)">';
  html += 'Loading map...';
  html += '</div>';
  html += '</div>';

  // Stop list
  html += '<div style="margin-top:12px">';
  html += '<h4 style="margin:0 0 10px;font-size:15px;color:var(--ap-text,#1e293b)">Route Stops</h4>';

  // Base start
  html += _routeStopCard(0, 'Base', data.base_address, '', '', '', true);

  data.stops.forEach(function(stop, idx) {
    var service = stop.service_type
      ? stop.service_type.replace(/_/g, ' ').replace(/\\b\\w/g, function(c) { return c.toUpperCase(); })
      : '';
    var rims = stop.num_rims ? stop.num_rims + ' rim(s)' : '';
    var meta = [service, rims].filter(Boolean).join(' - ');
    var travelNote = stop.travel_from_prev ? stop.travel_from_prev + ' min travel' : '';
    html += _routeStopCard(
      idx + 1,
      stop.customer_name || 'Customer',
      stop.address,
      stop.arrival_time,
      meta,
      travelNote,
      false
    );
  });

  // Base return
  html += _routeStopCard(data.stops.length + 1, 'Base (return)', data.base_address, '', '', '', true);

  html += '</div>';

  content.innerHTML = html;

  // Try to load Google Maps
  _initRouteMap(data);
}

function _routeStopCard(number, name, address, time, meta, travelNote, isBase) {
  var bgColor = isBase ? 'var(--ap-bg,#f1f5f9)' : 'var(--ap-surface,#fff)';
  var numColor = isBase ? '#6b7280' : '#C41230';
  var borderLeft = isBase ? '3px solid #d1d5db' : '3px solid #C41230';

  var html = '<div style="display:flex;gap:12px;padding:10px 12px;border-left:' + borderLeft + ';margin-bottom:4px;background:' + bgColor + ';border-radius:0 6px 6px 0">';
  html += '<div style="min-width:28px;height:28px;border-radius:50%;background:' + numColor + ';color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600">' + number + '</div>';
  html += '<div style="flex:1">';
  html += '<div style="font-weight:600;font-size:14px;color:var(--ap-text,#1e293b)">' + escapeHtml(name) + '</div>';
  html += '<div style="font-size:12px;color:var(--ap-text-muted,#64748b)">' + escapeHtml(address) + '</div>';
  if (meta) html += '<div style="font-size:12px;color:var(--ap-text-muted,#64748b)">' + escapeHtml(meta) + '</div>';
  html += '</div>';
  if (time) {
    html += '<div style="text-align:right">';
    html += '<div style="font-weight:600;font-size:14px;color:var(--ap-text,#1e293b)">' + escapeHtml(time) + '</div>';
    if (travelNote) html += '<div style="font-size:11px;color:var(--ap-text-muted,#94a3b8)">' + escapeHtml(travelNote) + '</div>';
    html += '</div>';
  }
  html += '</div>';
  return html;
}

// ── Summary bar ──────────────────────────────────────────────
function _updateRouteSummary(data) {
  var stopsEl = document.getElementById('route-stat-stops');
  var travelEl = document.getElementById('route-stat-travel');
  var distEl = document.getElementById('route-stat-distance');
  var timesEl = document.getElementById('route-stat-times');

  if (!data || !data.stops || data.stops.length === 0) {
    if (stopsEl) stopsEl.innerHTML = _routeStatHtml('0', 'Stops');
    if (travelEl) travelEl.innerHTML = _routeStatHtml('0 min', 'Travel Time');
    if (distEl) distEl.innerHTML = _routeStatHtml('0 km', 'Distance');
    if (timesEl) timesEl.innerHTML = _routeStatHtml('--', 'Schedule');
    return;
  }

  var numStops = data.stops.length;
  var travelMin = data.total_travel_minutes || 0;
  var distKm = data.total_distance_km || 0;

  // First and last times
  var firstTime = data.stops[0].arrival_time || '--';
  var lastTime = data.stops[numStops - 1].arrival_time || '--';
  var lastDuration = data.stops[numStops - 1].job_duration || 120;

  // Calculate end time of last job
  var endTime = '--';
  if (lastTime && lastTime !== '--') {
    var parts = lastTime.split(':');
    if (parts.length === 2) {
      var endMinutes = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10) + lastDuration;
      var endH = Math.floor(endMinutes / 60);
      var endM = endMinutes % 60;
      endTime = String(endH).padStart(2, '0') + ':' + String(endM).padStart(2, '0');
    }
  }

  if (stopsEl) stopsEl.innerHTML = _routeStatHtml(numStops, 'Stops');
  if (travelEl) travelEl.innerHTML = _routeStatHtml(travelMin + ' min', 'Travel Time');
  if (distEl) distEl.innerHTML = _routeStatHtml(distKm + ' km', 'Est. Distance');
  if (timesEl) timesEl.innerHTML = _routeStatHtml(firstTime + ' - ' + endTime, 'Schedule');
}

function _routeStatHtml(value, label) {
  return '<div style="font-size:18px;font-weight:700;color:var(--ap-text,#1e293b)">' + value + '</div>' +
    '<div style="font-size:11px;color:var(--ap-text-muted,#64748b);text-transform:uppercase;letter-spacing:0.5px">' + label + '</div>';
}

// ── Google Maps link ─────────────────────────────────────────
function _buildGoogleMapsLink(data) {
  var link = document.getElementById('route-gmaps-link');
  if (!link || !data || !data.stops || data.stops.length === 0) return;

  // Build Google Maps directions URL
  var waypoints = [data.base_address];
  data.stops.forEach(function(stop) {
    if (stop.address) waypoints.push(stop.address + ', Perth WA, Australia');
  });
  waypoints.push(data.base_address);

  var origin = encodeURIComponent(waypoints[0]);
  var destination = encodeURIComponent(waypoints[waypoints.length - 1]);
  var waypointStr = waypoints.slice(1, -1).map(function(w) {
    return encodeURIComponent(w);
  }).join('|');

  var url = 'https://www.google.com/maps/dir/?api=1' +
    '&origin=' + origin +
    '&destination=' + destination;
  if (waypointStr) {
    url += '&waypoints=' + waypointStr;
  }
  url += '&travelmode=driving';

  link.href = url;
  link.style.display = 'inline-flex';
}

// ── Google Maps initialization ───────────────────────────────
function _initRouteMap(data) {
  var canvas = document.getElementById('route-map-canvas');
  var fallback = document.getElementById('route-map-fallback');

  if (!data.maps_api_key) {
    // No API key — show static fallback
    _showStaticMapFallback(data);
    return;
  }

  // Check if Google Maps JS API is already loaded
  if (window.google && window.google.maps) {
    _renderGoogleMap(data);
    return;
  }

  // Load the Google Maps JS API dynamically
  if (fallback) fallback.textContent = 'Loading Google Maps...';

  // Check if script is already being loaded
  if (document.getElementById('google-maps-script')) {
    // Wait for it to load
    var checkInterval = setInterval(function() {
      if (window.google && window.google.maps) {
        clearInterval(checkInterval);
        _renderGoogleMap(data);
      }
    }, 200);
    setTimeout(function() { clearInterval(checkInterval); _showStaticMapFallback(data); }, 5000);
    return;
  }

  var script = document.createElement('script');
  script.id = 'google-maps-script';
  script.src = 'https://maps.googleapis.com/maps/api/js?key=' + data.maps_api_key + '&callback=_onGoogleMapsLoaded';
  script.async = true;
  script.defer = true;
  script.onerror = function() {
    _showStaticMapFallback(data);
  };

  window._onGoogleMapsLoaded = function() {
    _renderGoogleMap(data);
  };

  document.head.appendChild(script);

  // Fallback timeout
  setTimeout(function() {
    if (!window.google || !window.google.maps) {
      _showStaticMapFallback(data);
    }
  }, 8000);
}

function _renderGoogleMap(data) {
  var canvas = document.getElementById('route-map-canvas');
  if (!canvas || !window.google || !window.google.maps) return;

  canvas.innerHTML = '';

  // Perth center
  var center = { lat: -31.9505, lng: 115.8605 };
  var map = new google.maps.Map(canvas, {
    zoom: 11,
    center: center,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: true,
  });
  ROUTE_STATE.map = map;

  var bounds = new google.maps.LatLngBounds();
  var infoWindow = new google.maps.InfoWindow();
  ROUTE_STATE.infoWindow = infoWindow;

  // Geocode addresses and place markers
  var geocoder = new google.maps.Geocoder();
  var positions = [];
  var pending = data.stops.length + 1; // +1 for base

  function addMarker(position, label, title, contentHtml, isBase) {
    var marker = new google.maps.Marker({
      position: position,
      map: map,
      label: isBase ? { text: 'B', color: '#fff', fontWeight: '600' } : { text: String(label), color: '#fff', fontWeight: '600' },
      title: title,
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: isBase ? 14 : 16,
        fillColor: isBase ? '#6b7280' : '#C41230',
        fillOpacity: 1,
        strokeColor: '#fff',
        strokeWeight: 2,
      },
      zIndex: isBase ? 1 : 2,
    });

    marker.addListener('click', function() {
      infoWindow.setContent(contentHtml);
      infoWindow.open(map, marker);
    });

    ROUTE_STATE.markers.push(marker);
    bounds.extend(position);
  }

  function tryGeocode(address, callback) {
    geocoder.geocode({ address: address + ', Perth WA, Australia' }, function(results, status) {
      if (status === 'OK' && results[0]) {
        var loc = results[0].geometry.location;
        callback({ lat: loc.lat(), lng: loc.lng() });
      } else {
        callback(null);
      }
    });
  }

  function onAllGeocoded() {
    // Draw polyline
    if (positions.length > 1) {
      var validPositions = positions.filter(function(p) { return p !== null; });
      if (validPositions.length > 1) {
        ROUTE_STATE.polyline = new google.maps.Polyline({
          path: validPositions,
          geodesic: true,
          strokeColor: '#C41230',
          strokeOpacity: 0.8,
          strokeWeight: 3,
          icons: [{
            icon: { path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 3, strokeColor: '#C41230' },
            offset: '50%',
            repeat: '200px',
          }],
        });
        ROUTE_STATE.polyline.setMap(map);
      }
    }

    // Fit bounds
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
    }
  }

  // Geocode base address first
  tryGeocode(data.base_address, function(pos) {
    if (pos) {
      positions[0] = pos;
      addMarker(pos, 'B', 'Base: ' + data.base_address,
        '<div style="padding:4px"><strong>Base</strong><br>' + escapeHtml(data.base_address) + '</div>', true);
    } else {
      positions[0] = null;
    }
    pending--;
    if (pending === 0) onAllGeocoded();
  });

  // Geocode each stop
  data.stops.forEach(function(stop, idx) {
    var address = stop.address || '';
    positions[idx + 1] = null; // placeholder

    if (!address) {
      pending--;
      if (pending === 0) onAllGeocoded();
      return;
    }

    tryGeocode(address, function(pos) {
      if (pos) {
        positions[idx + 1] = pos;
        var service = stop.service_type
          ? stop.service_type.replace(/_/g, ' ').replace(/\\b\\w/g, function(c) { return c.toUpperCase(); })
          : 'Service';
        var infoHtml = '<div style="padding:4px;max-width:250px">' +
          '<strong>' + escapeHtml(stop.customer_name || 'Customer') + '</strong><br>' +
          '<span style="color:#64748b">' + escapeHtml(address) + '</span><br>' +
          '<span style="color:#C41230">' + escapeHtml(stop.arrival_time || '') + '</span> - ' +
          escapeHtml(service) +
          (stop.num_rims ? ' (' + stop.num_rims + ' rims)' : '') +
          '</div>';
        addMarker(pos, idx + 1, stop.customer_name || address, infoHtml, false);
      }
      pending--;
      if (pending === 0) onAllGeocoded();
    });
  });
}

// ── Static map fallback ──────────────────────────────────────
function _showStaticMapFallback(data) {
  var canvas = document.getElementById('route-map-canvas');
  if (!canvas) return;

  if (data.maps_api_key && data.stops && data.stops.length > 0) {
    // Use Google Static Maps API
    var markers = 'markers=color:gray|label:B|' + encodeURIComponent(data.base_address + ', Perth WA, Australia');
    data.stops.forEach(function(stop, idx) {
      if (stop.address) {
        markers += '&markers=color:red|label:' + (idx + 1) + '|' + encodeURIComponent(stop.address + ', Perth WA, Australia');
      }
    });

    // Build path
    var pathAddrs = [data.base_address + ', Perth WA, Australia'];
    data.stops.forEach(function(stop) {
      if (stop.address) pathAddrs.push(stop.address + ', Perth WA, Australia');
    });
    pathAddrs.push(data.base_address + ', Perth WA, Australia');
    var path = 'path=color:0xC41230ff|weight:3|' + pathAddrs.map(function(a) { return encodeURIComponent(a); }).join('|');

    var imgUrl = 'https://maps.googleapis.com/maps/api/staticmap?size=800x400&' + markers + '&' + path + '&key=' + data.maps_api_key;
    canvas.innerHTML = '<img src="' + imgUrl + '" style="width:100%;height:100%;object-fit:contain;border-radius:8px" alt="Route map">';
  } else {
    canvas.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--ap-text-muted,#64748b);flex-direction:column;gap:8px">' +
      '<div style="font-size:32px">&#128506;</div>' +
      '<div>Map unavailable (no API key configured)</div>' +
      '<div style="font-size:12px">Use the "Open in Google Maps" button above</div>' +
      '</div>';
  }
}

// ── Dashboard route card ─────────────────────────────────────
async function initRouteCard() {
  var container = document.getElementById('route-card-content');
  if (!container) return;

  container.innerHTML = '<div style="color:var(--ap-text-muted,#64748b);font-size:13px">Loading route info...</div>';

  var today = new Date().toISOString().slice(0, 10);
  var data = await fetchRouteData(today);

  if (!data || !data.stops || data.stops.length === 0) {
    container.innerHTML = '<div style="color:var(--ap-text-muted,#64748b);font-size:13px;text-align:center;padding:12px 0">No jobs scheduled today</div>';
    return;
  }

  var numStops = data.stops.length;
  var travelMin = data.total_travel_minutes || 0;
  var firstTime = data.stops[0].arrival_time || '--';
  var lastStop = data.stops[numStops - 1];
  var lastTime = lastStop.arrival_time || '--';
  var lastDuration = lastStop.job_duration || 120;

  // Calculate estimated end time
  var endTime = '--';
  if (lastTime && lastTime !== '--') {
    var parts = lastTime.split(':');
    if (parts.length === 2) {
      var endMinutes = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10) + lastDuration;
      var endH = Math.floor(endMinutes / 60);
      var endM = endMinutes % 60;
      endTime = String(endH).padStart(2, '0') + ':' + String(endM).padStart(2, '0');
    }
  }

  var html = '';
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">';
  html += '<div style="text-align:center;padding:8px;background:var(--ap-bg,#f8fafc);border-radius:6px">';
  html += '<div style="font-size:22px;font-weight:700;color:#C41230">' + numStops + '</div>';
  html += '<div style="font-size:11px;color:var(--ap-text-muted,#64748b);text-transform:uppercase">Jobs</div>';
  html += '</div>';
  html += '<div style="text-align:center;padding:8px;background:var(--ap-bg,#f8fafc);border-radius:6px">';
  html += '<div style="font-size:22px;font-weight:700;color:var(--ap-text,#1e293b)">' + travelMin + '<span style="font-size:13px;font-weight:400"> min</span></div>';
  html += '<div style="font-size:11px;color:var(--ap-text-muted,#64748b);text-transform:uppercase">Travel Time</div>';
  html += '</div>';
  html += '</div>';
  html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-top:1px solid var(--ap-border,#e2e8f0)">';
  html += '<div style="font-size:13px;color:var(--ap-text-muted,#64748b)">First job: <strong style="color:var(--ap-text,#1e293b)">' + escapeHtml(firstTime) + '</strong></div>';
  html += '<div style="font-size:13px;color:var(--ap-text-muted,#64748b)">Done by: <strong style="color:var(--ap-text,#1e293b)">' + escapeHtml(endTime) + '</strong></div>';
  html += '</div>';
  html += '<button onclick="openRouteMap()" class="ap-btn ap-btn-sm" style="width:100%;margin-top:10px;background:#C41230;color:#fff;border:none;cursor:pointer">View Route Map</button>';

  container.innerHTML = html;
}
"""
