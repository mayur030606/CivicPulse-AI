import Button from '../components/ui/Button.jsx'
import Card from '../components/ui/Card.jsx'

const capabilities = [
  {
    title: 'Speech-to-text',
    service: 'Gnani Prisma',
    description:
      'Transcribe voice complaints in Indian languages so residents can report issues by speaking.',
  },
  {
    title: 'Complaint understanding',
    service: 'Gnani Evon',
    description:
      'Extract category, priority, location hints and a concise summary from free-text complaints.',
  },
  {
    title: 'Text-to-speech',
    service: 'Gnani Timbre',
    description:
      'Read status updates back to citizens in their preferred language.',
  },
  {
    title: 'Image analysis',
    service: 'YOLO',
    description:
      'Detect potholes, garbage, congestion and other civic issues in uploaded photos.',
  },
  {
    title: 'Geo intelligence',
    service: 'Leaflet + OpenStreetMap',
    description:
      'Visualise complaints and traffic incidents on an interactive city map.',
  },
  {
    title: 'Multilingual by design',
    service: 'FastAPI + MySQL',
    description:
      'Store original language, transcripts and normalised categories for analytics.',
  },
]

const steps = [
  {
    step: '01',
    title: 'Capture',
    description: 'A citizen speaks, types or photographs a civic issue.',
  },
  {
    step: '02',
    title: 'Understand',
    description:
      'Speech, text and image models turn raw input into structured complaint data.',
  },
  {
    step: '03',
    title: 'Act',
    description:
      'Officials triage by priority and location, then update the citizen.',
  },
]

export default function HomePage() {
  return (
    <div className="space-y-16">
      <section className="grid items-center gap-8 lg:grid-cols-[1.15fr_0.85fr]">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full bg-civic-50 px-3 py-1 text-xs font-semibold text-civic-700 ring-1 ring-civic-200">
            <span className="h-1.5 w-1.5 rounded-full bg-civic-500" />
            Multilingual civic intelligence
          </p>
          <h1 className="mt-5 text-4xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-5xl">
            Your city, <span className="text-civic-600">heard clearly.</span>
          </h1>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-600">
            CivicPulse AI turns voice notes, messages and photos into structured
            complaints and traffic incident reports — in the language citizens
            actually use.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Button to="/report" size="lg">
              Report an issue
            </Button>
            <Button to="/map" variant="secondary" size="lg">
              Explore the map
            </Button>
          </div>
          <dl className="mt-10 grid max-w-lg grid-cols-3 gap-4 border-t border-slate-200 pt-6">
            {[
              ['8+', 'Languages planned'],
              ['4', 'AI services'],
              ['1', 'City dashboard'],
            ].map(([value, label]) => (
              <div key={label}>
                <dt className="text-2xl font-bold text-slate-900">{value}</dt>
                <dd className="mt-0.5 text-xs text-slate-500">{label}</dd>
              </div>
            ))}
          </dl>
        </div>

        <Card className="bg-gradient-to-br from-civic-700 to-civic-900 p-6 text-white">
          <p className="text-xs font-semibold uppercase tracking-wider text-civic-200">
            Live intake pipeline
          </p>
          <ol className="mt-5 space-y-4">
            {[
              ['Voice note', 'Prisma → transcript'],
              ['Photo', 'YOLO → issue tags'],
              ['Text', 'Evon → category + priority'],
              ['Citizen update', 'Timbre → spoken reply'],
            ].map(([input, output]) => (
              <li
                key={input}
                className="flex items-center justify-between gap-3 rounded-lg bg-white/10 px-4 py-3 text-sm ring-1 ring-white/10"
              >
                <span className="font-medium">{input}</span>
                <span className="text-civic-100">{output}</span>
              </li>
            ))}
          </ol>
          <p className="mt-5 text-xs leading-relaxed text-civic-200">
            Services are scaffolded. API contracts will be added from official
            Gnani documentation — no endpoints are assumed.
          </p>
        </Card>
      </section>

      <section>
        <h2 className="text-xl font-bold tracking-tight text-slate-900">
          How it works
        </h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          {steps.map((item) => (
            <Card key={item.step}>
              <span className="font-mono text-xs font-semibold text-civic-600">
                {item.step}
              </span>
              <h3 className="mt-2 font-semibold text-slate-900">{item.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-slate-600">
                {item.description}
              </p>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900">
              Built on a focused stack
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Every service has one job, so each can be swapped or scaled independently.
            </p>
          </div>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {capabilities.map((item) => (
            <Card key={item.title}>
              <p className="text-xs font-semibold uppercase tracking-wide text-civic-600">
                {item.service}
              </p>
              <h3 className="mt-1.5 font-semibold text-slate-900">{item.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-600">
                {item.description}
              </p>
            </Card>
          ))}
        </div>
      </section>
    </div>
  )
}
