import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  CheckCircle, XCircle, Plus, PencilSimple, Brain, Cube,
  ArrowRight, FloppyDisk, X, Trash, CheckFat, CaretDown,
  CaretUp, Lightning, Eye, EyeSlash, Spinner,
} from "@phosphor-icons/react";
import { toast } from "sonner";

// ─── Constants ────────────────────────────────────────────────────────────────
const MODEL_TYPE_META = {
  llm:       { label: "LLM · Chat",       icon: Brain, colorClass: "border-blue-500/40 bg-blue-500/10 text-blue-400" },
  embedding: { label: "Embedding · Search", icon: Cube,  colorClass: "border-purple-500/40 bg-purple-500/10 text-purple-400" },
};

const PROVIDER_PRESETS = {
  llm: [
    { value: "emergent",   label: "Emergent",    keyLabel: "EMERGENT_LLM_KEY",    models: ["gpt-4o-mini","gpt-4o","gpt-4-turbo","gpt-3.5-turbo"] },
    { value: "openrouter", label: "OpenRouter",  keyLabel: "OPENROUTER_API_KEY",  models: ["openai/gpt-4o-mini","openai/gpt-4o","anthropic/claude-3.5-sonnet","anthropic/claude-3-haiku","google/gemini-pro-1.5","meta-llama/llama-3.1-70b-instruct"] },
    { value: "openai",     label: "OpenAI",      keyLabel: "OPENAI_API_KEY",      models: ["gpt-4o","gpt-4o-mini","gpt-4-turbo","gpt-3.5-turbo"] },
    { value: "anthropic",  label: "Anthropic",   keyLabel: "ANTHROPIC_API_KEY",   models: ["claude-3-5-sonnet-20241022","claude-3-haiku-20240307","claude-opus-4-5"] },
    { value: "custom",     label: "Custom",      keyLabel: "API Key",             models: [] },
  ],
  embedding: [
    { value: "local",  label: "Local (ONNX)", keyLabel: null,           models: ["all-MiniLM-L6-v2"] },
    { value: "openai", label: "OpenAI",       keyLabel: "OPENAI_API_KEY", models: ["text-embedding-3-small","text-embedding-3-large","text-embedding-ada-002"] },
    { value: "custom", label: "Custom",       keyLabel: "API Key",      models: [] },
  ],
};

const ROLE_DISPLAY = { admin: "Admin", editor: "Editor", viewer: "Viewer", guest: "Guest" };

// ─── Helpers ──────────────────────────────────────────────────────────────────
function roleDisplay(role) {
  return ROLE_DISPLAY[role] ?? role;
}

// ─── Model Card ───────────────────────────────────────────────────────────────
function ModelCard({ model, onEdit, onActivate, onDelete, activating }) {
  const meta = MODEL_TYPE_META[model.model_type] || MODEL_TYPE_META.llm;
  const Icon = meta.icon;
  const isActive = model.is_active;

  return (
    <div className={`relative border bg-card transition-all duration-200 ${isActive ? "border-foreground/40" : "border-border hover:border-foreground/20"}`}>
      {isActive && (
        <div className="absolute -top-px left-4 text-[9px] font-mono uppercase tracking-widest bg-foreground text-background px-2 py-0.5">
          Active
        </div>
      )}
      <div className="p-5 pt-6">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2.5">
            <div className={`w-9 h-9 flex items-center justify-center border ${meta.colorClass}`}>
              <Icon size={16} weight="fill" />
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{meta.label}</div>
              <div className="font-semibold text-sm leading-tight mt-0.5">{model.name}</div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => onEdit(model)} title="Edit" className="w-6 h-6 flex items-center justify-center text-muted-foreground hover:text-foreground border border-transparent hover:border-border transition-all rounded-sm">
              <PencilSimple size={12} />
            </button>
            {!isActive && (
              <button onClick={() => onDelete(model)} title="Delete" className="w-6 h-6 flex items-center justify-center text-muted-foreground hover:text-red-400 border border-transparent hover:border-red-400/30 transition-all rounded-sm">
                <Trash size={12} />
              </button>
            )}
          </div>
        </div>

        <div className="font-mono text-[11px] text-muted-foreground bg-muted/40 px-2 py-1.5 border border-border/50 truncate mb-2">
          {model.model_id}
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="capitalize">{model.provider}</span>
            {model.has_api_key && (
              <span className="flex items-center gap-0.5 text-green-500/70">
                · <CheckCircle size={10} weight="fill" /> Key set
              </span>
            )}
          </div>
          {!isActive && (
            <button
              onClick={() => onActivate(model)}
              disabled={activating === model.id}
              className="text-[10px] font-mono text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors disabled:opacity-50"
            >
              {activating === model.id ? <Spinner size={10} className="animate-spin" /> : <Lightning size={10} weight="fill" />}
              Set active
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Add/Edit Model Modal ─────────────────────────────────────────────────────
function ModelModal({ open, onClose, editModel, onSaved }) {
  const modelType = editModel?.model_type ?? null;
  const [step, setStep] = useState(modelType ? "form" : "type"); // "type" | "form"
  const [selectedType, setSelectedType] = useState(modelType || "llm");
  const [form, setForm] = useState({
    name: "", provider: "", model_id: "", api_key: "", api_base_url: "", is_active: false, notes: "",
  });
  const [showKey, setShowKey] = useState(false);
  const [customModel, setCustomModel] = useState("");
  const [tab, setTab] = useState("basic");
  const [saving, setSaving] = useState(false);

  const isEdit = !!editModel;

  useEffect(() => {
    if (open) {
      setShowKey(false);
      setTab("basic");
      if (editModel) {
        setStep("form");
        setSelectedType(editModel.model_type);
        setForm({
          name: editModel.name || "",
          provider: editModel.provider || "",
          model_id: editModel.model_id || "",
          api_key: "",  // never pre-fill key
          api_base_url: editModel.api_base_url || "",
          is_active: editModel.is_active || false,
          notes: editModel.notes || "",
        });
        setCustomModel(editModel.model_id || "");
      } else {
        setStep(modelType ? "form" : "type");
        setSelectedType(modelType || "llm");
        setForm({ name: "", provider: "", model_id: "", api_key: "", api_base_url: "", is_active: false, notes: "" });
        setCustomModel("");
      }
    }
  }, [open, editModel]);

  const providerList = PROVIDER_PRESETS[selectedType] || [];
  const providerMeta = providerList.find(p => p.value === form.provider);
  const modelList = providerMeta?.models || [];

  const handleProviderChange = (val) => {
    const meta = (PROVIDER_PRESETS[selectedType] || []).find(p => p.value === val);
    const firstModel = meta?.models?.[0] || "";
    setForm(f => ({ ...f, provider: val, model_id: firstModel }));
    setCustomModel(firstModel);
  };

  const handleModelSelect = (val) => {
    if (val === "__custom__") {
      setForm(f => ({ ...f, model_id: customModel }));
    } else {
      setForm(f => ({ ...f, model_id: val }));
      setCustomModel(val);
    }
  };

  const isCustomModel = modelList.length === 0 || !modelList.includes(form.model_id);

  const handleSave = async () => {
    if (!form.name.trim()) { toast.error("Name is required"); return; }
    if (!form.provider) { toast.error("Provider is required"); return; }
    if (!form.model_id.trim()) { toast.error("Model ID is required"); return; }

    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        model_type: selectedType,
        provider: form.provider,
        model_id: form.model_id.trim(),
        is_active: form.is_active,
        notes: form.notes || null,
      };
      if (form.api_key && form.api_key.trim()) payload.api_key = form.api_key.trim();
      if (form.api_base_url && form.api_base_url.trim()) payload.api_base_url = form.api_base_url.trim();

      let result;
      if (isEdit) {
        const r = await api.patch(`/admin/models/${editModel.id}`, payload);
        result = r.data;
        toast.success("Model updated");
      } else {
        const r = await api.post("/admin/models", payload);
        result = r.data;
        toast.success("Model added");
      }
      onSaved(result, isEdit);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg p-0 gap-0 overflow-hidden border border-border bg-background">
        {/* Header */}
        <div className="border-b border-border px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            {step === "type" ? (
              <span className="text-foreground font-medium">Select Model Type</span>
            ) : (
              <>
                <button onClick={() => !isEdit && setStep("type")} className={!isEdit ? "hover:text-foreground transition-colors cursor-pointer" : ""}>
                  Select Type
                </button>
                <ArrowRight size={12} />
                <span className="text-foreground font-medium capitalize">
                  {isEdit ? `Edit: ${editModel.name}` : `Add ${selectedType.toUpperCase()}`}
                </span>
              </>
            )}
          </div>
          <button onClick={onClose} className="w-6 h-6 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors">
            <X size={14} />
          </button>
        </div>

        {/* Step 1 — pick type */}
        {step === "type" && (
          <div className="px-6 py-6 space-y-3">
            <p className="text-xs text-muted-foreground mb-4">What kind of model do you want to add?</p>
            {Object.entries(MODEL_TYPE_META).map(([type, meta]) => {
              const Icon = meta.icon;
              return (
                <button
                  key={type}
                  onClick={() => { setSelectedType(type); setStep("form"); }}
                  className="w-full text-left border border-border hover:border-foreground/40 p-4 flex items-center gap-4 transition-all group"
                >
                  <div className={`w-10 h-10 flex items-center justify-center border ${meta.colorClass}`}>
                    <Icon size={18} weight="fill" />
                  </div>
                  <div>
                    <div className="font-medium text-sm">{meta.label.split(" · ")[0]} Model</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">{meta.label}</div>
                  </div>
                  <ArrowRight size={14} className="ml-auto text-muted-foreground group-hover:translate-x-0.5 transition-transform" />
                </button>
              );
            })}
          </div>
        )}

        {/* Step 2 — form */}
        {step === "form" && (
          <>
            {/* Tabs */}
            <div className="border-b border-border px-6 flex">
              {["basic", "advanced"].map(t => (
                <button key={t} onClick={() => setTab(t)}
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors capitalize -mb-px ${t === tab ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                  {t === "basic" ? "Basic Information" : "Advanced Settings"}
                </button>
              ))}
            </div>

            <div className="px-6 py-5 space-y-4 max-h-[65vh] overflow-y-auto">
              {tab === "basic" && (
                <>
                  {/* Name */}
                  <div className="space-y-1.5">
                    <Label className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">
                      Display Name <span className="text-red-400">*</span>
                    </Label>
                    <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                      placeholder="e.g. GPT-4o Production" className="font-mono text-sm" />
                  </div>

                  {/* Type badge (read-only) */}
                  <div className="space-y-1.5">
                    <Label className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">Model Type</Label>
                    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 border text-xs font-mono ${MODEL_TYPE_META[selectedType]?.colorClass}`}>
                      {React.createElement(MODEL_TYPE_META[selectedType]?.icon, { size: 11, weight: "fill" })}
                      {selectedType.toUpperCase()}
                    </div>
                  </div>

                  {/* Provider */}
                  <div className="space-y-1.5">
                    <Label className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">
                      Provider <span className="text-red-400">*</span>
                    </Label>
                    <Select value={form.provider} onValueChange={handleProviderChange}>
                      <SelectTrigger className="font-mono text-sm"><SelectValue placeholder="Select provider…" /></SelectTrigger>
                      <SelectContent>
                        {providerList.map(p => (
                          <SelectItem key={p.value} value={p.value} className="font-mono text-sm">{p.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Model selector */}
                  {form.provider && modelList.length > 0 && (
                    <div className="space-y-1.5">
                      <Label className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">
                        Base Model <span className="text-muted-foreground/50 normal-case text-[10px] ml-1">— or enter custom below</span>
                      </Label>
                      <Select
                        value={modelList.includes(form.model_id) ? form.model_id : "__custom__"}
                        onValueChange={handleModelSelect}
                      >
                        <SelectTrigger className="font-mono text-sm"><SelectValue placeholder="Select model…" /></SelectTrigger>
                        <SelectContent>
                          {modelList.map(m => <SelectItem key={m} value={m} className="font-mono text-xs">{m}</SelectItem>)}
                          <SelectItem value="__custom__" className="font-mono text-xs text-muted-foreground">Custom (enter below)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  {/* Model ID input */}
                  {form.provider && (isCustomModel || modelList.length === 0) && (
                    <div className="space-y-1.5">
                      <Label className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">
                        Model ID <span className="text-red-400">*</span>
                      </Label>
                      <Input
                        value={form.model_id}
                        onChange={e => { setForm(f => ({ ...f, model_id: e.target.value })); setCustomModel(e.target.value); }}
                        placeholder="e.g. gpt-4o-mini"
                        className="font-mono text-sm"
                      />
                    </div>
                  )}

                  {/* API Key */}
                  {form.provider && form.provider !== "local" && (
                    <div className="space-y-1.5">
                      <Label className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                        {providerMeta?.keyLabel || "API Key"}
                        {isEdit && editModel?.has_api_key && (
                          <span className="text-green-500/70 flex items-center gap-0.5 ml-1 normal-case font-normal text-[10px]">
                            <CheckCircle size={9} weight="fill" /> Key saved — leave blank to keep
                          </span>
                        )}
                      </Label>
                      <div className="relative">
                        <Input
                          type={showKey ? "text" : "password"}
                          value={form.api_key}
                          onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                          placeholder={isEdit && editModel?.has_api_key ? "Leave blank to keep existing key" : "sk-…"}
                          className="font-mono text-sm pr-9"
                        />
                        <button
                          type="button"
                          onClick={() => setShowKey(s => !s)}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                        >
                          {showKey ? <EyeSlash size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Set as active toggle */}
                  <div className="flex items-center gap-3 pt-1">
                    <button
                      type="button"
                      onClick={() => setForm(f => ({ ...f, is_active: !f.is_active }))}
                      className={`w-9 h-5 rounded-full transition-colors relative ${form.is_active ? "bg-foreground" : "bg-muted"}`}
                    >
                      <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-background transition-all ${form.is_active ? "left-4" : "left-0.5"}`} />
                    </button>
                    <Label className="text-xs text-muted-foreground cursor-pointer" onClick={() => setForm(f => ({ ...f, is_active: !f.is_active }))}>
                      Set as active model (applies immediately)
                    </Label>
                  </div>
                </>
              )}

              {tab === "advanced" && (
                <>
                  <div className="space-y-1.5">
                    <Label className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">
                      Custom Base URL <span className="text-muted-foreground/50 normal-case text-[10px] ml-1">— override provider endpoint</span>
                    </Label>
                    <Input
                      value={form.api_base_url}
                      onChange={e => setForm(f => ({ ...f, api_base_url: e.target.value }))}
                      placeholder="https://api.example.com/v1"
                      className="font-mono text-sm"
                    />
                    <p className="text-[11px] text-muted-foreground">For self-hosted or proxied OpenAI-compatible endpoints.</p>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">Notes</Label>
                    <Input
                      value={form.notes}
                      onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                      placeholder="Optional notes about this config…"
                      className="text-sm"
                    />
                  </div>
                  <div className="border border-border divide-y divide-border mt-2">
                    <div className="px-3 py-2.5">
                      <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-1">API Key storage</div>
                      <div className="text-[11px] text-muted-foreground">Keys are stored in MongoDB. In production, enable encryption at rest on your MongoDB cluster.</div>
                    </div>
                    <div className="px-3 py-2.5">
                      <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-1">Runtime application</div>
                      <div className="text-[11px] text-muted-foreground">Setting a model as Active pushes the config into the running process immediately — no restart needed.</div>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Footer */}
            <div className="border-t border-border px-6 py-4 flex items-center justify-end gap-3">
              <Button variant="ghost" size="sm" onClick={onClose} className="text-muted-foreground">Cancel</Button>
              <Button size="sm" onClick={handleSave} disabled={saving || !form.name.trim() || !form.provider || !form.model_id.trim()} className="flex items-center gap-1.5">
                {saving ? <Spinner size={13} className="animate-spin" /> : <FloppyDisk size={13} weight="bold" />}
                {saving ? "Saving…" : isEdit ? "Update" : "Add Model"}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Feature Flags Section ────────────────────────────────────────────────────
function FeatureFlagsSection({ flags }) {
  const [open, setOpen] = useState(false);
  const entries = Object.entries(flags);
  const onCount = entries.filter(([, v]) => v).length;

  return (
    <section>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between group"
      >
        <div className="dc-overline">Feature Flags</div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="text-green-500 font-mono">{onCount} on</span>
            <span className="text-muted-foreground/40">·</span>
            <span className="font-mono">{entries.length - onCount} off</span>
          </div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground group-hover:text-foreground transition-colors">
            {open ? <><CaretUp size={12} /> Hide</> : <><CaretDown size={12} /> Show</>}
          </div>
        </div>
      </button>

      {open && (
        <div className="mt-3">
          <p className="text-xs text-muted-foreground mb-3">Toggled server-side via env vars. Read-only view.</p>
          <div className="border border-border">
            {entries.map(([k, v], i) => (
              <div
                key={k}
                className={`grid grid-cols-[1fr_100px] items-center px-4 py-2 ${i < entries.length - 1 ? "border-b border-border" : ""}`}
                data-testid={`flag-row-${k}`}
              >
                <div className="font-mono text-[12px] text-muted-foreground">{k}</div>
                <div className="flex items-center gap-1.5 text-xs font-mono justify-end">
                  {v
                    ? <span className="text-green-500 flex items-center gap-1"><CheckCircle size={13} weight="fill" /> ON</span>
                    : <span className="text-muted-foreground/50 flex items-center gap-1"><XCircle size={13} weight="fill" /> OFF</span>
                  }
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// ─── Main Settings Page ───────────────────────────────────────────────────────
export default function Settings() {
  const { user } = useAuth();
  const [flags, setFlags] = useState({});
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editModel, setEditModel] = useState(null);
  const [activating, setActivating] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const isOwner = user?.role === "admin";

  const loadModels = useCallback(async () => {
    try {
      const r = await api.get("/admin/models");
      setModels(r.data);
    } catch {
      /* non-fatal */
    }
  }, []);

  useEffect(() => {
    api.get("/v2/flags").then(r => setFlags(r.data)).catch(() => {});
    if (isOwner) {
      loadModels().finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [isOwner, loadModels]);

  const handleAddModel = () => { setEditModel(null); setModalOpen(true); };
  const handleEditModel = (m) => { setEditModel(m); setModalOpen(true); };

  const handleSaved = (result, isEdit) => {
    setModels(prev => {
      // If active was toggled, clear siblings
      let updated = prev.map(m => {
        if (result.is_active && m.model_type === result.model_type && m.id !== result.id) {
          return { ...m, is_active: false };
        }
        return m;
      });
      if (isEdit) return updated.map(m => m.id === result.id ? result : m);
      return [result, ...updated];
    });
  };

  const handleActivate = async (model) => {
    setActivating(model.id);
    try {
      const r = await api.post(`/admin/models/${model.id}/activate`);
      setModels(prev => prev.map(m => ({
        ...m,
        is_active: m.model_type === model.model_type ? m.id === model.id : m.is_active,
      })));
      toast.success(`${r.data.name} is now active`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Activation failed");
    } finally {
      setActivating(null);
    }
  };

  const handleDelete = async (model) => {
    try {
      await api.delete(`/admin/models/${model.id}`);
      setModels(prev => prev.filter(m => m.id !== model.id));
      toast.success("Model deleted");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    } finally {
      setDeleteConfirm(null);
    }
  };

  const llmModels = models.filter(m => m.model_type === "llm");
  const embModels = models.filter(m => m.model_type === "embedding");

  return (
    <div>
      <header className="h-16 border-b border-border px-8 flex items-center sticky top-0 bg-background z-10">
        <div>
          <div className="dc-overline">Account</div>
          <h1 className="font-heading font-bold text-lg">Settings</h1>
        </div>
      </header>

      <div className="p-8 max-w-4xl space-y-10">

        {/* Profile */}
        <section>
          <div className="dc-overline mb-3">Profile</div>
          <div className="border border-border p-6 grid md:grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-muted-foreground">Name</div>
              <div className="font-medium mt-1" data-testid="settings-name">{user?.name}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Email</div>
              <div className="font-mono text-sm mt-1" data-testid="settings-email">{user?.email}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Role</div>
              <div className="mt-1">
                <Badge className="font-mono uppercase" data-testid="settings-role">
                  {roleDisplay(user?.role)}
                </Badge>
              </div>
            </div>
          </div>
        </section>

        {/* Models */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="dc-overline">Models</div>
            {isOwner && (
              <Button size="sm" onClick={handleAddModel} className="flex items-center gap-1.5 h-8 text-xs">
                <Plus size={12} weight="bold" /> Add Model
              </Button>
            )}
          </div>

          {loading ? (
            <div className="border border-border p-8 flex items-center justify-center text-muted-foreground text-sm">
              <Spinner size={16} className="animate-spin mr-2" /> Loading models…
            </div>
          ) : !isOwner ? (
            <p className="text-xs text-muted-foreground">Ask an Admin to manage models.</p>
          ) : models.length === 0 ? (
            <div className="border border-dashed border-border p-10 flex flex-col items-center justify-center text-center gap-3">
              <Brain size={28} className="text-muted-foreground/40" />
              <div className="text-sm font-medium text-muted-foreground">No models configured yet</div>
              <div className="text-xs text-muted-foreground/60 max-w-xs">
                Add your first LLM or embedding model. Models are stored in the database and apply at runtime.
              </div>
              <Button size="sm" onClick={handleAddModel} className="mt-1 flex items-center gap-1.5 h-8 text-xs">
                <Plus size={12} weight="bold" /> Add First Model
              </Button>
            </div>
          ) : (
            <div className="space-y-6">
              {llmModels.length > 0 && (
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1.5">
                    <Brain size={10} weight="fill" className="text-blue-400" /> LLM Models
                  </div>
                  <div className="grid md:grid-cols-2 gap-3">
                    {llmModels.map(m => (
                      <ModelCard key={m.id} model={m} onEdit={handleEditModel} onActivate={handleActivate} onDelete={setDeleteConfirm} activating={activating} />
                    ))}
                  </div>
                </div>
              )}
              {embModels.length > 0 && (
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1.5">
                    <Cube size={10} weight="fill" className="text-purple-400" /> Embedding Models
                  </div>
                  <div className="grid md:grid-cols-2 gap-3">
                    {embModels.map(m => (
                      <ModelCard key={m.id} model={m} onEdit={handleEditModel} onActivate={handleActivate} onDelete={setDeleteConfirm} activating={activating} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        {/* Feature Flags */}
        <FeatureFlagsSection flags={flags} />

      </div>

      {/* Add/Edit Modal */}
      <ModelModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        editModel={editModel}
        onSaved={handleSaved}
      />

      {/* Delete confirm dialog */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent className="max-w-sm border border-border bg-background p-6">
          <div className="space-y-3">
            <div className="font-semibold">Delete model?</div>
            <div className="text-sm text-muted-foreground">
              <span className="font-mono text-foreground">{deleteConfirm?.name}</span> will be permanently removed from the database.
            </div>
            <div className="flex gap-2 justify-end pt-2">
              <Button variant="ghost" size="sm" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
              <Button size="sm" variant="destructive" onClick={() => handleDelete(deleteConfirm)}>Delete</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
