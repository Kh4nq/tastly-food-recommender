type FoodKind = "beef-soup" | "chicken-soup" | "vegetable-soup" | "noodle-soup" | "fried-noodles" | "shrimp-noodles" | "rice" | "hotpot" | "salad" | "bread" | "cake" | "meal";

export function foodIllustrationKind(name: string, category?: string): FoodKind {
  const dish = name.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d");
  if (/pad thai|mi xao|bun xao|stir.?fried/.test(dish)) return /tom|shrimp|prawn/.test(dish) ? "shrimp-noodles" : "fried-noodles";
  if (/pho|bun|hu tieu|ramen|chao|sup|congee|soup/.test(dish) || category === "noodle" || category === "soup") {
    if (/chay|nam|vegetarian|mushroom/.test(dish)) return "vegetable-soup";
    if (/ga|chicken/.test(dish)) return "chicken-soup";
    if (/bo|beef/.test(dish)) return "beef-soup";
    return "noodle-soup";
  }
  if (category === "hotpot" || /lau|hot ?pot/.test(dish)) return "hotpot";
  if (category === "rice" || /com|xoi|rice/.test(dish)) return "rice";
  if (category === "salad" || /goi|salad/.test(dish)) return "salad";
  if (category === "dessert" || /chocolate|cake|banh ngot/.test(dish)) return "cake";
  if (category === "bakery" || /banh mi|bread/.test(dish)) return "bread";
  return "meal";
}

function Herbs() {
  return <g fill="#7b9b68"><ellipse cx="225" cy="217" rx="13" ry="26" transform="rotate(-45 225 217)" /><ellipse cx="243" cy="204" rx="11" ry="22" transform="rotate(18 243 204)" /><ellipse cx="253" cy="225" rx="21" ry="10" transform="rotate(-15 253 225)" /><path d="m224 237 19-29" stroke="#566f48" strokeWidth="3" strokeLinecap="round" /></g>;
}

function Noodles({ fried = false }: { fried?: boolean }) {
  return <g fill="none" stroke={fried ? "#dda45c" : "#f9e5b5"} strokeWidth="9" strokeLinecap="round">
    <path d="M235 239q23-38 45-5t45-6 47 4" /><path d="M249 258q22-33 45-4t45-6 44 4" /><path d="M268 212q18-20 37 3t38-3" />
  </g>;
}

function Shrimp({ x, y, rotate = 0 }: { x: number; y: number; rotate?: number }) {
  return <g transform={`translate(${x} ${y}) rotate(${rotate})`}><path d="M15-15C-18-34-37 5-16 22 1 35 27 16 15 1" fill="none" stroke="#e78c5c" strokeWidth="16" strokeLinecap="round" /><path d="m-18-14 8 10m-16 4 12 3m-7 13 11-5" stroke="#ffd5ac" strokeWidth="4" strokeLinecap="round" /><path d="m13-11 19-12-1 17Z" fill="#cf7050" /></g>;
}

export default function FoodIllustration({ name, category, label }: { name: string; category?: string; label: string }) {
  const kind = foodIllustrationKind(name, category);
  const bowl = kind.endsWith("soup") || kind === "hotpot";
  const fried = kind === "fried-noodles" || kind === "shrimp-noodles";
  return <svg role="img" aria-label={label} data-food-illustration={kind} viewBox="0 0 640 480" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" xmlns="http://www.w3.org/2000/svg">
    <rect width="640" height="480" fill={kind === "salad" ? "#edf0e2" : kind === "cake" ? "#f7e9df" : "#f7eddf"} />
    <ellipse cx="320" cy="365" rx="181" ry="25" fill="#bd9c7e" opacity=".18" />
    {bowl ? <>
      <g fill="none" stroke="#d5b99c" strokeWidth="5" strokeLinecap="round"><path d="M277 148q-14-17 1-35m38 24q-14-17 1-35m37 46q-14-17 1-35" /></g>
      {kind === "hotpot" && <g fill="#b36e54"><rect x="124" y="248" width="49" height="23" rx="10" /><rect x="467" y="248" width="49" height="23" rx="10" /></g>}
      <ellipse cx="320" cy="348" rx="182" ry="35" fill="#fffbf3" />
      <path d="M161 230c6 91 62 129 159 129s153-38 159-129Z" fill={kind === "vegetable-soup" ? "#8eaa7d" : "#cb8068"} />
      <path d="M183 274q137 46 274 0" fill="none" stroke="#ffe9d3" strokeWidth="4" opacity=".45" />
      <ellipse cx="320" cy="231" rx="160" ry="61" fill="#fff9ec" /><ellipse cx="320" cy="231" rx="138" ry="45" fill={kind === "hotpot" ? "#dca06d" : "#d9b781"} />
      <Noodles /><Herbs />
      {kind === "beef-soup" && <g fill="#a96c55" stroke="#e3ae8d" strokeWidth="4"><ellipse cx="359" cy="213" rx="30" ry="14" transform="rotate(-24 359 213)" /><ellipse cx="391" cy="239" rx="29" ry="14" transform="rotate(-28 391 239)" /><path d="m340 214 33-10m-2 39 34-15" fill="none" /></g>}
      {kind === "chicken-soup" && <g fill="#f8dfab" stroke="#e4bf7f" strokeWidth="3"><path d="m337 206 23-11 35 33-17 13Z" /><path d="m349 239 18-9 29 31-17 7Z" /><path d="m326 228 16-7 17 17-17 7Z" /></g>}
      {kind === "vegetable-soup" && <g fill="#a78263" stroke="#6f5843" strokeWidth="3"><path d="M345 219q16-37 42 0Z" /><path d="M361 219v17h10v-17" fill="#f4dfbf" /><path d="M380 245q14-30 35 0Z" /><path d="M394 245v13h8v-13" fill="#f4dfbf" /></g>}
      {(kind === "noodle-soup" || kind === "hotpot") && <><ellipse cx="376" cy="220" rx="26" ry="19" transform="rotate(-25 376 220)" fill="#fff8df" /><circle cx="376" cy="220" r="11" fill="#e9ac4b" /></>}
      <g fill="#647b50"><circle cx="283" cy="222" r="4" /><circle cx="328" cy="252" r="4" /><circle cx="302" cy="204" r="3" /></g>
      <g fill="#795346"><circle cx="302" cy="315" r="3" /><circle cx="338" cy="315" r="3" /><path d="M314 323q6 6 12 0" fill="none" stroke="#795346" strokeWidth="2.5" strokeLinecap="round" /></g>
    </> : kind === "cake" ? <>
      <ellipse cx="320" cy="336" rx="185" ry="40" fill="#fffaf3" /><ellipse cx="320" cy="332" rx="145" ry="27" fill="none" stroke="#e6cfb8" strokeWidth="3" />
      <path d="m220 239 150-51 59 98-146 57-63-39Z" fill="#82563f" /><path d="m220 275 63 35 146-55v15l-146 57-63-36Z" fill="#d4a27b" /><path d="m220 239 150-51 59 38-146 56Z" fill="#52392f" />
      <path d="M290 226c-18-8-16-26-1-30-7-14 11-25 21-14 12-10 25 5 16 17 14 10 2 25-11 23Z" fill="#fff2db" /><circle cx="309" cy="181" r="10" fill="#bd5c45" /><path d="M309 172q-2-15 12-20" fill="none" stroke="#7b9467" strokeWidth="4" strokeLinecap="round" />
    </> : <>
      <ellipse cx="320" cy="282" rx="188" ry="84" fill="#fffaf0" /><ellipse cx="320" cy="280" rx="156" ry="63" fill="none" stroke="#e5d3b8" strokeWidth="4" />
      {fried ? <><ellipse cx="319" cy="270" rx="114" ry="42" fill="#eacb8d" /><Noodles fried /><Herbs />{kind === "shrimp-noodles" ? <><Shrimp x={357} y={229} rotate={-15} /><Shrimp x={380} y={279} rotate={30} /></> : <g fill="#f0d7a2"><rect x="351" y="218" width="23" height="19" rx="5" transform="rotate(20 351 218)" /><rect x="374" y="250" width="22" height="20" rx="5" /></g>}<path d="m390 214 27-11-3 31Z" fill="#95ad72" stroke="#d1df9d" strokeWidth="4" /></>
        : kind === "salad" ? <><g fill="#8da976"><ellipse cx="279" cy="254" rx="52" ry="23" transform="rotate(-30 279 254)" /><ellipse cx="344" cy="255" rx="65" ry="26" transform="rotate(30 344 255)" /><ellipse cx="317" cy="287" rx="74" ry="22" /></g><g fill="#da8665"><circle cx="275" cy="272" r="18" /><circle cx="359" cy="280" r="16" /><circle cx="322" cy="238" r="13" /></g><g fill="#ebd7a1"><ellipse cx="308" cy="271" rx="13" ry="5" transform="rotate(-30 308 271)" /><ellipse cx="348" cy="250" rx="13" ry="5" /></g></>
        : kind === "bread" ? <><g transform="rotate(-20 320 267)"><rect x="207" y="220" width="227" height="89" rx="44" fill="#d4a365" /><path d="M218 270q101-30 204 0" fill="none" stroke="#7c9c64" strokeWidth="14" /><path d="m266 233 12 20m35-23 12 20m35-23 12 20" stroke="#f8dfaa" strokeWidth="8" strokeLinecap="round" /></g></>
        : <><path d="M230 280q0-80 75-80t75 80Z" fill="#fff0d0" /><g fill="#ddc995"><ellipse cx="281" cy="230" rx="7" ry="3" transform="rotate(30 281 230)" /><ellipse cx="320" cy="247" rx="7" ry="3" transform="rotate(-30 320 247)" /><ellipse cx="278" cy="263" rx="7" ry="3" /></g><ellipse cx="373" cy="279" rx="40" ry="25" fill="#bd7f56" transform="rotate(-20 373 279)" /><path d="m350 273 32-12m-23 26 32-12" stroke="#e7b885" strokeWidth="4" strokeLinecap="round" /><Herbs /></>}
    </>}
  </svg>;
}
