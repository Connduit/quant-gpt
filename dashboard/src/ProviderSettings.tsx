import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "./api";
import { Badge, ErrorBox } from "./components";

interface Provider {
  id: string;
  configured: boolean;
  saved: boolean;
  source: "dashboard" | "environment" | "none";
  host: string;
}

export function ProviderSettings() {
  const query = useQueryClient();
  const [alpacaKey, setAlpacaKey] = useState("");
  const [alpacaSecret, setAlpacaSecret] = useState("");
  const [databentoKey, setDatabentoKey] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const status = useQuery({
    queryKey: ["provider-settings"],
    queryFn: () =>
      request<{ items: Provider[]; editable: boolean }>("/settings/providers"),
  });
  const secure =
    window.location.protocol === "https:" ||
    ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
  const editable = !!status.data?.editable && secure && !pending;
  const providers = status.data?.items ?? [];
  async function update(provider: string, values?: Record<string, string>) {
    setPending(true);
    setMessage("");
    try {
      await request(`/settings/providers/${provider}`, {
        method: values ? "PUT" : "DELETE",
        body: JSON.stringify({ ...values, confirmed: true }),
      });
      if (provider === "alpaca") {
        setAlpacaKey("");
        setAlpacaSecret("");
      } else setDatabentoKey("");
      setMessage(
        values
          ? "API keys saved. New download jobs use them immediately."
          : "Saved keys removed. Any keys supplied by the server environment still apply.",
      );
      await Promise.all([
        query.invalidateQueries({ queryKey: ["provider-settings"] }),
        query.invalidateQueries({ queryKey: ["historical-providers"] }),
      ]);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  function indicator(id: string) {
    const provider = providers.find((p) => p.id === id);
    return (
      <p className="subtle">
        <Badge
          text={provider?.configured ? "KEYS_CONFIGURED" : "NOT_CONFIGURED"}
        />
        {provider?.configured &&
          ` Source: ${provider.source === "dashboard" ? "saved in dashboard" : "server environment"}.`}{" "}
        Configuration status does not verify account access or entitlements.
      </p>
    );
  }
  const input = {
    type: "password",
    autoComplete: "new-password",
    minLength: 8,
    maxLength: 512,
    required: true,
    disabled: !editable,
    spellCheck: false,
  };
  return (
    <>
      <div className="heading">
        <div>
          <p>DATA PROVIDERS</p>
          <h1>Provider API keys</h1>
          <p>Connect Alpaca and Databento for historical data downloads.</p>
        </div>
      </div>
      <section className="panel">
        <h3>Manage data credentials</h3>
        <p>
          Keys are encrypted on the server and never returned to this page. New
          download jobs use saved keys without restarting the dashboard.
        </p>
        {!secure && (
          <p className="warning-line">
            Open this website over HTTPS before entering API keys. Localhost
            connections are also supported.
          </p>
        )}
        {!status.data?.editable && !status.isPending && !status.error && (
          <p className="warning-line">
            Connect with an operator access token in the top bar to save or
            remove keys. Researcher tokens authorize downloads, but cannot edit
            credentials.
          </p>
        )}
        {status.error && (
          <ErrorBox error={status.error} retry={() => void status.refetch()} />
        )}
        <p role="status" aria-live="polite">
          {message}
        </p>
      </section>
      <section className="panel equity-workflow">
        <h3>Alpaca</h3>
        {indicator("alpaca")}
        <form
          aria-label="Alpaca credentials"
          onSubmit={(e) => {
            e.preventDefault();
            void update("alpaca", {
              key_id: alpacaKey.trim(),
              secret_key: alpacaSecret.trim(),
            });
          }}
        >
          <div className="workflow-fields">
            <label>
              Alpaca API key ID
              <input
                {...input}
                value={alpacaKey}
                onChange={(e) => setAlpacaKey(e.target.value)}
              />
            </label>
            <label>
              Alpaca secret key
              <input
                {...input}
                value={alpacaSecret}
                onChange={(e) => setAlpacaSecret(e.target.value)}
              />
            </label>
          </div>
          <p className="subtle">
            Enter both fields to replace the saved pair. These keys are used for
            market data, not order submission.
          </p>
          <div className="controls">
            <button type="submit" disabled={!editable}>
              Save Alpaca keys
            </button>
            <button
              type="button"
              disabled={
                !editable || !providers.find((p) => p.id === "alpaca")?.saved
              }
              onClick={() => void update("alpaca")}
            >
              Remove Alpaca keys
            </button>
          </div>
        </form>
      </section>
      <section className="panel equity-workflow">
        <h3>Databento</h3>
        {indicator("databento")}
        <form
          aria-label="Databento credentials"
          onSubmit={(e) => {
            e.preventDefault();
            void update("databento", { api_key: databentoKey.trim() });
          }}
        >
          <div className="workflow-fields">
            <label>
              Databento API key
              <input
                {...input}
                value={databentoKey}
                onChange={(e) => setDatabentoKey(e.target.value)}
              />
            </label>
          </div>
          <p className="subtle">
            Your historical-download cost cap stays in the Data library form.
            Saving a key does not start a paid download.
          </p>
          <div className="controls">
            <button type="submit" disabled={!editable}>
              Save Databento key
            </button>
            <button
              type="button"
              disabled={
                !editable || !providers.find((p) => p.id === "databento")?.saved
              }
              onClick={() => void update("databento")}
            >
              Remove Databento key
            </button>
          </div>
        </form>
      </section>
      <section className="panel">
        <h3>Network access</h3>
        <p>
          Your hosting environment must allow HTTPS to{" "}
          <code>data.alpaca.markets</code> and <code>hist.databento.com</code>.
          Saving keys does not change its firewall or allowlist.
        </p>
        <p>
          Saved keys take precedence over environment keys for the same
          provider. Removing saved keys restores the environment configuration.
          Existing running jobs keep the credentials they started with.
        </p>
      </section>
    </>
  );
}
