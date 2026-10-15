"use client"; // Error boundaries must be Client Components

// Last resort when the root layout itself throws (header and footer included).
// It replaces the whole document: no providers, no Tailwind, no global CSS, so inline styles
export default function GlobalError({
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <html lang="vi">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          fontFamily: "system-ui, sans-serif",
          background: "#faf3ea",
          color: "#1f1b16",
          textAlign: "center",
        }}
      >
        <div style={{ maxWidth: 420 }}>
          <h1 style={{ margin: 0, fontSize: 24 }}>
            Có sự cố rồi / Something went wrong
          </h1>
          {/* No cookie access here, so both languages are shown */}
          <p style={{ marginTop: 12, lineHeight: 1.6, color: "#666" }}>
            Hệ thống đang bận hoặc chưa kết nối được. Bạn thử lại sau ít phút nhé.
            <br />
            The service is busy or unreachable. Please try again in a few minutes.
          </p>
          <button
            type="button"
            onClick={() => retry()}
            style={{
              marginTop: 24,
              border: 0,
              borderRadius: 999,
              padding: "12px 24px",
              background: "#c0392b",
              color: "#fff",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Thử lại / Try again
          </button>
        </div>
      </body>
    </html>
  );
}
