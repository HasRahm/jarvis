// mc-app.jsx — Mounts the design canvas with 3 Mission Control variants + Tweaks panel.

const PALETTES = {
  hud:     { accent: '#FFB547', accent2: '#5EEAD4', anomaly: '#FFB547', border: 'rgba(255,181,71,0.15)' },
  cyber:   { accent: '#5EEAD4', accent2: '#FFB547', anomaly: '#F87171', border: 'rgba(255,255,255,0.08)' },
  iris:    { accent: '#7DD3FC', accent2: '#C4B5FD', anomaly: '#FFB547', border: 'rgba(255,255,255,0.08)' },
  ember:   { accent: '#FB923C', accent2: '#F472B6', anomaly: '#FACC15', border: 'rgba(251,146,60,0.18)' },
  mint:    { accent: '#34D399', accent2: '#7DD3FC', anomaly: '#FBBF24', border: 'rgba(52,211,153,0.18)' },
};

const DEFAULTS = /*EDITMODE-BEGIN*/{
  "vizMode": "orb",
  "density": "comfortable",
  "palette": "hud",
  "showCanvas": true
}/*EDITMODE-END*/;

function MissionControlApp() {
  const [t, setTweak] = useTweaks(DEFAULTS);

  const palette = PALETTES[t.palette] || PALETTES.hud;

  // Each variant maintains its own engine state.
  // They each render at 1440x920 inside the canvas artboards.
  return (
    <>
      <DesignCanvas>
        <DCSection id="mission-control" title="Mission Control" subtitle="Three desktop directions · Cinematic Jarvis · Iron Man inspired">
          <DCArtboard id="v1-hud" label="A · HUD Cinematic" width={1440} height={920}>
            <MCVariantHUD width={1440} height={920}
              palette={t.palette === 'hud' ? undefined : palette}
              density={t.density} vizMode={t.vizMode} />
          </DCArtboard>
          <DCArtboard id="v2-console" label="B · Operator Console" width={1440} height={920}>
            <MCVariantConsole width={1440} height={920}
              palette={t.palette === 'hud' ? undefined : palette}
              density={t.density} vizMode={t.vizMode} />
          </DCArtboard>
          <DCArtboard id="v3-spatial" label="C · Holographic Spatial" width={1440} height={920}>
            <MCVariantSpatial width={1440} height={920}
              palette={t.palette === 'hud' ? undefined : palette}
              density={t.density} vizMode={t.vizMode} />
          </DCArtboard>
        </DCSection>
      </DesignCanvas>

      <TweaksPanel title="Tweaks · Mission Control">
        <TweakSection label="Visualizer">
          <TweakRadio label="Style" value={t.vizMode}
            onChange={(v) => setTweak('vizMode', v)}
            options={[
              { value: 'orb',       label: 'Orb' },
              { value: 'waveform',  label: 'Wave' },
              { value: 'particles', label: 'Particles' },
            ]} />
        </TweakSection>
        <TweakSection label="Density">
          <TweakRadio label="Layout" value={t.density}
            onChange={(v) => setTweak('density', v)}
            options={[
              { value: 'compact',     label: 'Compact' },
              { value: 'comfortable', label: 'Comfy' },
              { value: 'spacious',    label: 'Spacious' },
            ]} />
        </TweakSection>
        <TweakSection label="Palette">
          <TweakSelect label="Theme" value={t.palette}
            onChange={(v) => setTweak('palette', v)}
            options={[
              { value: 'hud',   label: 'HUD · amber / teal' },
              { value: 'cyber', label: 'Cyber · teal / amber' },
              { value: 'iris',  label: 'Iris · cyan / violet' },
              { value: 'ember', label: 'Ember · orange / pink' },
              { value: 'mint',  label: 'Mint · green / cyan' },
            ]} />
        </TweakSection>
        <TweakSection label="Notes">
          <div style={{ fontSize: 11, lineHeight: 1.55, color: 'rgba(255,255,255,0.55)' }}>
            Each artboard runs its own simulation. Click <b>Engage</b> on any variant to watch a fake
            DAG execute end-to-end (with auto-heal at the QA step).
          </div>
        </TweakSection>
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<MissionControlApp />);
