import { useState } from "react";
import { Avatar, Reveal, Select, Spinner } from "../components/ui";
import { deleteJson, endpoints, invalidate, postJson, useApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import { shortDate } from "../lib/format";

export default function TeamPage() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useApi(endpoints.team());
  const [invite, setInvite] = useState({ name: "", email: "", role: "collections" });
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(null);

  const mayManage = data?.may_manage ?? user?.role === "admin";

  async function refresh(message) {
    invalidate("/org");
    await reload({ fresh: true });
    setFlash(message);
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setFlash(null);
    try {
      const result = await postJson("/org/team", {
        name: invite.name.trim(),
        email: invite.email.trim(),
        role: invite.role,
      });
      setInvite({ name: "", email: "", role: "collections" });
      await refresh(`Added. Temporary password: ${result.temporary_password}`);
    } catch (err) {
      setFlash(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(member) {
    setBusy(true);
    try {
      await deleteJson(`/org/team/${member.id}`);
      await refresh(`${member.name} no longer has access.`);
    } catch (err) {
      setFlash(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) {
    return (
      <div className="page-loading">
        <Spinner size={20} />
        <span className="source">Loading your team…</span>
      </div>
    );
  }
  if (error) return <p className="page__error">{error}</p>;

  const members = data?.members ?? [];
  const roles = data?.roles ?? [];

  return (
    <div className="page">
      <section className="page__head">
        <div>
          <p className="eyebrow eyebrow--signal">{data?.organisation?.name}</p>
          <p className="page__lead">
            Everyone with access to this book, and what they can do with it.
          </p>
        </div>
        <div className="page__head-stats">
          <HeadStat label="People" value={String(members.length)} />
          <HeadStat
            label="Collections officers"
            value={String(members.filter((m) => m.role === "collections" || m.role === "field").length)}
          />
          <HeadStat label="Attempts logged" value={String(data?.attempts_logged ?? 0)} />
        </div>
      </section>

      {flash ? <p className="flash">{flash}</p> : null}

      <div className="team">
        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Members</span>
            <span className="source">{mayManage ? "you can manage access" : "read only"}</span>
          </div>

          <ul className="team__list">
            {members.map((member, index) => (
              <Reveal as="li" className="team__member" key={member.id} delay={index * 45}>
                <Avatar name={member.name} tone={member.tone} size={38} />
                <div className="team__identity">
                  <span className="team__name">
                    {member.name}
                    {member.is_you ? <span className="team__you">you</span> : null}
                  </span>
                  <span className="team__email">{member.email}</span>
                </div>
                <div className="team__meta">
                  <span className="chip chip--quiet">{member.role_label}</span>
                  <span className="team__seen">
                    {member.last_seen_at ? `seen ${shortDate(member.last_seen_at.slice(0, 10))}` : "never signed in"}
                  </span>
                </div>
                {mayManage && !member.is_you ? (
                  <button
                    type="button"
                    className="team__remove"
                    disabled={busy}
                    onClick={() => remove(member)}
                  >
                    Remove
                  </button>
                ) : (
                  <span className="team__remove team__remove--placeholder" />
                )}
              </Reveal>
            ))}
          </ul>
        </section>

        <div className="team__side">
          {mayManage ? (
            <section className="panel panel--action">
              <div className="panel__head">
                <span className="panel__title">Add someone</span>
                <span className="source">they get a temporary password</span>
              </div>
              <form className="team__form" onSubmit={submit}>
                <label className="field">
                  <span className="eyebrow">Name</span>
                  <input
                    value={invite.name}
                    onChange={(event) => setInvite({ ...invite, name: event.target.value })}
                    placeholder="Ngozi Eze"
                    required
                  />
                </label>
                <label className="field">
                  <span className="eyebrow">Work email</span>
                  <input
                    type="email"
                    value={invite.email}
                    onChange={(event) => setInvite({ ...invite, email: event.target.value })}
                    placeholder="ngozi@lender.ng"
                    required
                  />
                </label>
                <Select
                  label="Role"
                  value={invite.role}
                  onChange={(value) => setInvite({ ...invite, role: value })}
                  options={roles.map((role) => ({
                    value: role.code,
                    label: role.label,
                    hint: role.code,
                  }))}
                />
                <button className="btn btn--signal" type="submit" disabled={busy}>
                  {busy ? "Adding…" : "Add to team"}
                </button>
              </form>
            </section>
          ) : null}

          <section className="panel">
            <div className="panel__head">
              <span className="panel__title">What each role sees</span>
            </div>
            <ul className="roles">
              {roles.map((role) => (
                <li key={role.code}>
                  <span className="roles__name">{role.label}</span>
                  <span className="roles__desc">{role.description}</span>
                </li>
              ))}
            </ul>
            <p className="note">
              Borrower records and the live queue require a signed-in session. Aggregate portfolio
              reporting is public, which is the line a lender would draw.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

function HeadStat({ label, value }) {
  return (
    <div className="headstat">
      <span className="eyebrow">{label}</span>
      <span className="figure figure--md">{value}</span>
    </div>
  );
}
