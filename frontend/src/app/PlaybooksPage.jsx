import { endpoints, useApi } from "../lib/api";
import { money, percent } from "../lib/format";

export default function PlaybooksPage() {
  const { data, error, loading } = useApi(endpoints.playbooks());

  if (loading && !data) return <p className="page__note">Loading playbooks…</p>;
  if (error) return <p className="page__error">{error}</p>;

  const thresholds = data?.priority_thresholds;

  return (
    <div className="page">
      <section className="page__head">
        <div>
          <p className="eyebrow eyebrow--signal">Playbook library</p>
          <p className="page__lead">
            Nine playbooks, each with an owner, a script and a stated success measure — plus the
            conversion rate the expected-value engine assumes for it, by delinquency band. These
            assumptions are the product&rsquo;s most arguable numbers, so they are printed rather than
            buried.
          </p>
        </div>
        <div className="page__head-stats">
          <HeadStat label="Playbooks" value={String((data?.playbooks ?? []).length)} />
          <HeadStat
            label="Priority: high"
            value={money(thresholds?.high ?? 0)}
            note="expected recovery or more"
            tone="var(--resolve)"
          />
          <HeadStat label="Priority: medium" value={money(thresholds?.medium ?? 0)} />
        </div>
      </section>

      <section className="panel">
        <div className="panel__head">
          <span className="panel__title">Channels and unit cost</span>
          <span className="source">direct cost plus officer time</span>
        </div>
        <div className="channels">
          {(data?.channels ?? []).map((channel) => (
            <div className="channel" key={channel.code}>
              <span className="channel__name">{channel.code.replace(/_/g, " ")}</span>
              <span className="channel__cost tnum">{money(channel.cost)}</span>
              <span className="source">
                direct {money(channel.direct_cost)} · {channel.officer_minutes} min
              </span>
            </div>
          ))}
        </div>
      </section>

      <div className="playbook-list">
        {(data?.playbooks ?? []).map((playbook) => {
          const stat = data?.performance?.[playbook.code];
          return (
            <article className="playbook-card" key={playbook.code}>
              <header>
                <div>
                  <span className="eyebrow">{playbook.owner}</span>
                  <h3 className="playbook-card__name">{playbook.name}</h3>
                </div>
                <span className={`chip ${playbook.phase === "recovery" ? "chip--risk" : "chip--signal"}`}>
                  {playbook.phase.replace(/_/g, " ")}
                </span>
              </header>

              <p className="playbook-card__objective">{playbook.objective}</p>

              <div className="playbook-card__grid">
                <div>
                  <span className="eyebrow">Timing</span>
                  <p>{playbook.timing}</p>
                </div>
                <div>
                  <span className="eyebrow">Success means</span>
                  <p>{playbook.success_metric}</p>
                </div>
                <div>
                  <span className="eyebrow">Channel</span>
                  <p>
                    {playbook.channel.replace(/_/g, " ")} · {money(playbook.channel_cost)}
                  </p>
                </div>
                <div>
                  <span className="eyebrow">Logged attempts</span>
                  <p>
                    {stat?.attempts ?? 0}
                    {stat?.kept_rate !== null && stat?.kept_rate !== undefined
                      ? ` · ${percent(stat.kept_rate, 0)} kept`
                      : ""}
                  </p>
                </div>
              </div>

              <blockquote className="playbook-card__script">{playbook.script}</blockquote>

              <div className="playbook-card__bands">
                {playbook.effectiveness_by_band.map((band) => (
                  <div className="bandbar" key={band.band}>
                    <span className="bandbar__label">{band.band}</span>
                    <span className="bandbar__track">
                      <span
                        className="bandbar__fill"
                        style={{ width: `${band.probability * 100}%` }}
                      />
                    </span>
                    <span className="bandbar__value tnum">{percent(band.probability * 100, 0)}</span>
                  </div>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function HeadStat({ label, value, note, tone }) {
  return (
    <div className="headstat">
      <span className="eyebrow">{label}</span>
      <span className="figure figure--md" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      {note ? <span className="stat__note">{note}</span> : null}
    </div>
  );
}
