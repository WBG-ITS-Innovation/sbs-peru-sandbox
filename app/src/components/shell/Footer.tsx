// Footer — rendered only inside the audit route's nested layout per
// the WS4 directive. Renders the WBG attribution.

interface FooterProps {
  attribution: string;
}

export function Footer({ attribution }: FooterProps) {
  return (
    <footer className="border-t border-border bg-surface-subtle px-4 py-2 text-2xs text-fg-muted">
      {attribution}
    </footer>
  );
}
