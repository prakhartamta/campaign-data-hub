// Inline SVG, copied from the design handoff's icons.md. No icon library, no image requests.
//
// Every icon is decorative: each one sits beside a visible word, so a reader who cannot tell
// amber from green still gets the status from the text. That is why they are all aria-hidden.

/** pass | warn | fail | missing, plus `error` — a check that raised, drawn as a failure. */
export type StatusKind = string;

export function StatusIcon({ status, size = 16 }: { status: StatusKind; size?: number }) {
  const common = {
    viewBox: "0 0 16 16",
    width: size,
    height: size,
    "aria-hidden": true,
    className: "status-icon",
  } as const;

  if (status === "pass") {
    return (
      <svg {...common}>
        <circle cx="8" cy="8" r="7" fill="#1a7f45" />
        <path
          d="M4.8 8.2l2.1 2.1 4.3-4.5"
          stroke="#fff"
          strokeWidth="1.8"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  if (status === "warn") {
    return (
      <svg {...common}>
        <path d="M8 1.5L15 14H1z" fill="#b26b00" stroke="#b26b00" strokeLinejoin="round" />
        <path d="M8 6v3.6" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="8" cy="11.8" r="0.9" fill="#fff" />
      </svg>
    );
  }

  if (status === "missing") {
    return (
      <svg {...common}>
        <circle
          cx="8"
          cy="8"
          r="6.25"
          fill="none"
          stroke="#4b5563"
          strokeWidth="1.5"
          strokeDasharray="2.5 2"
        />
        <path d="M5.5 8h5" stroke="#4b5563" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }

  // fail, and `error` with it.
  return (
    <svg {...common}>
      <circle cx="8" cy="8" r="7" fill="#c0281b" />
      <path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function SelectChevron() {
  return (
    <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
      <path
        d="M2.5 4.5L6 8l3.5-3.5"
        stroke="#5a6474"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Both chevrons are rendered; CSS shows the one matching the <details> state. */
export function DisclosureChevrons() {
  return (
    <>
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="chevron-right">
        <path
          d="M6 3.5L10.5 8 6 12.5"
          stroke="#3d4654"
          strokeWidth="1.6"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="chevron-down">
        <path
          d="M3.5 6L8 10.5 12.5 6"
          stroke="#3d4654"
          strokeWidth="1.6"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </>
  );
}

export function Spinner() {
  return (
    <svg
      viewBox="0 0 16 16"
      width="14"
      height="14"
      aria-hidden="true"
      style={{ animation: "cdh-spin .8s linear infinite", flex: "none" }}
    >
      <circle cx="8" cy="8" r="6" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="2" />
      <path d="M8 2a6 6 0 0 1 6 6" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/** Three platform nodes on the left feed one hub node on the right. */
export function LogoMark() {
  return (
    <svg viewBox="0 0 28 28" width="28" height="28" aria-hidden="true">
      <rect width="28" height="28" rx="7" fill="#1f5fbf" />
      <path
        d="M7.5 8C13 8 14 14 19.5 14M7.5 14H19.5M7.5 20C13 20 14 14 19.5 14"
        stroke="#fff"
        strokeOpacity=".75"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="7" cy="8" r="2" fill="#fff" />
      <circle cx="7" cy="14" r="2" fill="#fff" />
      <circle cx="7" cy="20" r="2" fill="#fff" />
      <circle cx="20.5" cy="14" r="3.5" fill="#fff" />
      <circle cx="20.5" cy="14" r="1.4" fill="#1f5fbf" />
    </svg>
  );
}
