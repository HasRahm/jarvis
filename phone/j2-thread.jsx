/* j2-thread.jsx — conversation panel + composer */
const { useState: useJ2ThreadState, useEffect: useJ2ThreadEffect, useRef: useJ2ThreadRef } = React;

function J2TypingDots() {
  return <div className="j2-typing"><span/><span/><span/></div>;
}

function J2Message({ msg }) {
  const [shown, setShown] = useJ2ThreadState(msg.stream ? "" : msg.text);
  const [typing, setTyping] = useJ2ThreadState(!!msg.stream);

  useJ2ThreadEffect(() => {
    if (!msg.stream) { setShown(msg.text); return; }
    let i = 0;
    const words = msg.text.split(" ");
    setTyping(true);
    const dot = setTimeout(() => {
      const iv = setInterval(() => {
        i += 1;
        setShown(words.slice(0, i).join(" "));
        if (i >= words.length) { clearInterval(iv); setTyping(false); }
      }, 34);
    }, 420);
    return () => clearTimeout(dot);
  }, []);

  if (msg.role === "user") {
    return (
      <div className="j2-msg-block user">
        <div className="j2-bubble user">{msg.text}</div>
      </div>
    );
  }
  return (
    <div className="j2-msg-block jarvis">
      <div className="j2-msg-from"><Logo size={22} /><span>Jarvis</span></div>
      {typing && shown === "" ? <J2TypingDots /> : <div className="j2-bubble jarvis">{shown}</div>}
    </div>
  );
}

function J2Composer({ onSend, placeholder, big }) {
  const [val, setVal] = useJ2ThreadState("");
  const taRef = useJ2ThreadRef(null);

  const grow = () => {
    const ta = taRef.current; if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 180) + "px";
  };
  const submit = () => {
    const v = val.trim(); if (!v) return;
    onSend(v); setVal("");
    if (taRef.current) taRef.current.style.height = "auto";
  };

  return (
    <div className={`j2-composer ${big ? "big" : ""}`}>
      <textarea
        ref={taRef}
        className="j2-composer-input"
        rows={1}
        value={val}
        placeholder={placeholder || "Describe what to build…"}
        onChange={e => { setVal(e.target.value); grow(); }}
        onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
      />
      <div className="j2-composer-bar">
        <button className="j2-composer-mic" title="Voice"><IconMic size={17} /></button>
        <div className="j2-composer-hint">Jarvis orchestrates agents · ⏎ to run</div>
        <button className="j2-composer-send" disabled={!val.trim()} onClick={submit} title="Run">
          <IconArrow size={17} />
        </button>
      </div>
    </div>
  );
}

function J2Thread({ messages, onSend, running }) {
  const endRef = useJ2ThreadRef(null);
  useJ2ThreadEffect(() => {
    if (endRef.current) endRef.current.parentNode.scrollTop = endRef.current.parentNode.scrollHeight;
  }, [messages]);
  return (
    <div className="j2-thread">
      <div className="j2-thread-scroll">
        {messages.map(m => <J2Message key={m.id} msg={m} />)}
        <div ref={endRef} />
      </div>
      <div className="j2-thread-foot">
        <J2Composer onSend={onSend} placeholder={running ? "Add a follow-up or correction…" : "Describe what to build…"} />
      </div>
    </div>
  );
}

Object.assign(window, { J2Thread, J2Composer, J2Message });
