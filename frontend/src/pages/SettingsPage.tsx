import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { coreApi } from "../api";
import { Card, ErrorNotice, Loading, PageTitle, StatusBadge } from "../components/ui";

export function SettingsPage() {
  const client = useQueryClient();
  const catalog = useQuery({ queryKey: ["models"], queryFn: coreApi.models });
  const select = useMutation({ mutationFn: ({ provider, model, thinking }: { provider: string; model: string; thinking: boolean | null }) => coreApi.selectModel(provider, model, thinking), onSuccess: () => { client.invalidateQueries({ queryKey: ["models"] }); client.invalidateQueries({ queryKey: ["workspace"] }); } });
  if (catalog.isLoading) return <Loading />;
  if (catalog.error) return <ErrorNotice error={catalog.error} />;
  return <div><PageTitle eyebrow="Reasoning boundary" title="Model selection" /><div className="grid gap-5 lg:grid-cols-[.7fr_1.3fr]"><Card><h2 className="font-display text-xl font-semibold">Provider health</h2><div className="mt-4 grid gap-3">{catalog.data?.providers.map((provider) => <div key={provider.provider} className="flex items-center justify-between"><div><div className="font-medium">{provider.provider}</div><div className="text-xs text-ink-3">{provider.detail}</div></div><StatusBadge status={provider.available ? "available" : "unavailable"} /></div>)}</div></Card><div className="grid content-start gap-3">{catalog.data?.candidates.map((model) => <button key={`${model.provider}:${model.model}:${model.thinking}`} disabled={!catalog.data.providers.find((provider) => provider.provider === model.provider)?.available || select.isPending} onClick={() => select.mutate({ provider: model.provider, model: model.model, thinking: model.thinking ?? null })} className={`rounded-xl border p-4 text-left disabled:opacity-50 ${model.is_selected ? "border-primary bg-primary/5" : "border-rule bg-surface"}`}><div className="flex items-center justify-between"><div className="font-medium">{model.model}</div>{model.is_selected ? <StatusBadge status="selected" /> : null}</div><div className="mt-1 text-xs text-ink-3">{model.provider} · {model.label || "chat model"}{model.thinking === null || model.thinking === undefined ? "" : model.thinking ? " · thinking" : " · direct"}</div></button>)}</div></div>{select.error ? <div className="mt-5"><ErrorNotice error={select.error} /></div> : null}</div>;
}
