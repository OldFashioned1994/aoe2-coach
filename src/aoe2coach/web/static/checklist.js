// Avance de la checklist: click en cualquier lado, barra espaciadora o flechas.
// Sin librerías: mientras jugás, esto sólo tiene que mostrar el paso que viene.
(function () {
  const pasos = Array.from(document.querySelectorAll(".cl-paso"));
  if (!pasos.length) return;

  const barra = document.getElementById("barra");
  const indice = document.getElementById("indice");
  let actual = 0;

  function mostrar(i) {
    actual = Math.max(0, Math.min(pasos.length - 1, i));
    pasos.forEach((p, n) => p.classList.toggle("activo", n === actual));
    barra.style.width = ((actual + 1) / pasos.length) * 100 + "%";
    indice.textContent = actual + 1;
  }

  document.getElementById("siguiente").addEventListener("click", (e) => {
    e.stopPropagation();
    mostrar(actual + 1);
  });
  document.getElementById("anterior").addEventListener("click", (e) => {
    e.stopPropagation();
    mostrar(actual - 1);
  });
  document.addEventListener("click", () => mostrar(actual + 1));
  document.addEventListener("keydown", (e) => {
    if ([" ", "ArrowRight", "ArrowDown", "Enter"].includes(e.key)) {
      e.preventDefault();
      mostrar(actual + 1);
    }
    if (["ArrowLeft", "ArrowUp", "Backspace"].includes(e.key)) {
      e.preventDefault();
      mostrar(actual - 1);
    }
  });

  mostrar(0);
})();
