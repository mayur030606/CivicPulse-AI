export const COMPLAINT_CATEGORIES = [
  { value: 'roads', label: 'Roads & potholes' },
  { value: 'garbage', label: 'Garbage & sanitation' },
  { value: 'water', label: 'Water supply' },
  { value: 'electricity', label: 'Street lighting & electricity' },
  { value: 'drainage', label: 'Drainage & flooding' },
  { value: 'traffic', label: 'Traffic & parking' },
  { value: 'public_safety', label: 'Public safety' },
  { value: 'other', label: 'Other' },
]

/**
 * Values shared by ``IncidentCreate`` and the deterministic classifier's
 * ``ComplaintCategory`` enum. Keep these values in sync with the backend.
 */
export const INCIDENT_CATEGORIES = [
  { value: 'pothole', label: 'Roads & potholes' },
  { value: 'garbage', label: 'Garbage & sanitation' },
  { value: 'water_leakage', label: 'Water supply & leakage' },
  { value: 'streetlight', label: 'Street lighting & electricity' },
  { value: 'drainage', label: 'Drainage & flooding' },
  { value: 'traffic_accident', label: 'Traffic accident' },
  { value: 'road_blockage', label: 'Road blockage & congestion' },
  { value: 'other', label: 'Other' },
]

export const COMPLAINT_STATUSES = [
  { value: 'submitted', label: 'Submitted' },
  { value: 'in_review', label: 'In review' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'rejected', label: 'Rejected' },
]

/**
 * Canonical incident status values confirmed by the backend workflow.
 *
 * The backend stores incident status as a title-case string and restricts
 * updates to these four values. Keep this list in sync with
 * backend/app/models/enums.py.
 */
export const INCIDENT_STATUSES = [
  { value: 'Submitted', label: 'Submitted' },
  { value: 'In Progress', label: 'In Progress' },
  { value: 'Resolved', label: 'Resolved' },
  { value: 'Closed', label: 'Closed' },
]

export const SEVERITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
]

export const PRIORITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
]

export const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'hi', label: 'हिन्दी (Hindi)' },
  { value: 'gu', label: 'ગુજરાતી (Gujarati)' },
  { value: 'mr', label: 'मराठी (Marathi)' },
  { value: 'ta', label: 'தமிழ் (Tamil)' },
  { value: 'te', label: 'తెలుగు (Telugu)' },
  { value: 'kn', label: 'ಕನ್ನಡ (Kannada)' },
  { value: 'bn', label: 'বাংলা (Bengali)' },
]

/**
 * Language codes accepted by the backend voice endpoint
 * (``gnani_prisma.SUPPORTED_LANGUAGE_CODES``). These are intentionally
 * separate from ``LANGUAGES``: the voice provider uses BCP-47 style codes and
 * supports ``indic-auto`` for automatic detection.
 */
export const VOICE_LANGUAGES = [
  { value: 'indic-auto', label: 'Auto-detect (recommended)' },
  { value: 'bn-IN', label: 'বাংলা (Bengali)' },
  { value: 'en-IN', label: 'English' },
  { value: 'gu-IN', label: 'ગુજરાતી (Gujarati)' },
  { value: 'hi-IN', label: 'हिन्दी (Hindi)' },
  { value: 'kn-IN', label: 'ಕನ್ನಡ (Kannada)' },
  { value: 'ml-IN', label: 'മലയാളം (Malayalam)' },
  { value: 'mr-IN', label: 'मराठी (Marathi)' },
  { value: 'pa-IN', label: 'ਪੰਜਾਬੀ (Punjabi)' },
  { value: 'ta-IN', label: 'தமிழ் (Tamil)' },
  { value: 'te-IN', label: 'తెలుగు (Telugu)' },
]

/**
 * Language codes supported by the backend Timbre TTS endpoint
 * (``gnani_timbre.SUPPORTED_LANGUAGES``). Timbre v2.5 voices are
 * language-specific, so only these confirmed languages are exposed.
 */
export const TTS_LANGUAGES = [
  { value: 'en-IN', label: 'English' },
  { value: 'hi-IN', label: 'हिन्दी (Hindi)' },
  { value: 'mr-IN', label: 'मराठी (Marathi)' },
]

export const STATUS_STYLES = {
  submitted: 'bg-slate-100 text-slate-700 ring-slate-200',
  in_review: 'bg-amber-100 text-amber-800 ring-amber-200',
  in_progress: 'bg-blue-100 text-blue-800 ring-blue-200',
  resolved: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  closed: 'bg-slate-200 text-slate-700 ring-slate-300',
  rejected: 'bg-rose-100 text-rose-800 ring-rose-200',
}

export const PRIORITY_STYLES = {
  low: 'bg-slate-100 text-slate-700 ring-slate-200',
  medium: 'bg-sky-100 text-sky-800 ring-sky-200',
  high: 'bg-orange-100 text-orange-800 ring-orange-200',
  critical: 'bg-rose-100 text-rose-800 ring-rose-200',
}
