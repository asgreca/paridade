#!/usr/bin/env python3
"""OPCIONAL. Gera as fotos de abertura dos capítulos do site com a API de imagens da OpenAI.
Não faz parte da análise: nenhum número depende deste script.

Chave de API: copie .env.example para .env (na raiz do repositório) e preencha OPENAI_API_KEY,
ou exporte a variável no terminal. A chave nunca é impressa nem gravada em outro lugar.
  cp .env.example .env            # e edite o .env
  python extras/imagens.py        # gera as que faltam em site_img/<capitulo>.jpg
  python extras/imagens.py --refazer gap,mapa
"""
import base64, json, os, pathlib, shutil, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

P = pathlib.Path(__file__).resolve().parent.parent
IMG = P / "site_img"
MODELO = os.environ.get("PARIDADE_IMG_MODELO", "gpt-image-2")

ESTILO = ("Fotografia editorial cinematográfica e hiper-realista, formato horizontal, luz natural suave com sombras profundas, "
          "fundo escuro quase preto (#121212), granulação sutil de filme, muito espaço negativo à esquerda para título. "
          "Paleta restrita: preto, cinzas, verde (#4CAF50) e amarelo (#FBC02D) como únicos acentos de cor, em detalhes de luz ou objetos. "
          "Contexto: mercado de trabalho brasileiro. Sem texto legível, sem letras, sem números, sem logotipos, sem marcas; "
          "pessoas apenas de costas, em silhueta ou fora de foco, nunca com rosto identificável. Cena: ")

CENAS = {
    "hero": "escritório amplo ao anoitecer, um homem e uma mulher de costas trabalhando lado a lado em mesas idênticas, telas acesas, uma luminária verde e outra amarela.",
    "gap": "duas pastas de holerite idênticas e fechadas sobre uma mesa escura, entre elas uma régua de metal; luz lateral; uma pasta com fita verde e outra com fita amarela.",
    "tempo": "relógio de ponto industrial antigo na parede de uma fábrica, ao lado um capacete de segurança amarelo, luvas e um colete refletivo pendurados, luz fria lateral.",
    "bracal": "canteiro de obra ao entardecer, um operário e uma operária de capacete, ambos de costas, poeira no ar iluminada pelo sol baixo.",
    "generos": "bancada com objetos de várias profissões lado a lado: estetoscópio, giz e apagador, capacete de obra, chave inglesa, teclado de computador e prancheta, luz de cima dramática.",
    "profissoes": "corredor de hospital à noite com uma enfermeira de costas caminhando, luz verde suave das portas, piso refletindo, fundo desfocado.",
    "carreira": "escadaria interna de um prédio de escritórios, uma mulher de costas subindo com uma bolsa e uma mochila infantil, luz amarela entrando pela janela no topo.",
    "mapa": "mapa do Brasil em relevo de gesso sobre uma mesa escura, iluminado por pequenos pontos de luz amarela e verde, sem nenhuma inscrição.",
    "teses": "livro grosso fechado sobre uma mesa de leitura com uma luminária de mesa acesa, óculos ao lado, xícara de café, biblioteca escura ao fundo, capa sem título visível.",
    "imprensa": "pilha de jornais dobrados sem manchetes legíveis sobre uma mesa, microfones de entrevista coletiva desfocados ao fundo, luz de refletor.",
    "veredito": "balança antiga de dois pratos em latão, quase equilibrada, sobre uma mesa escura, um prato com luz verde e outro com luz amarela, fundo preto.",
    "grupo": "duas mesas de trabalho idênticas lado a lado num escritório vazio à noite, mesmas cadeiras, mesmos computadores apagados, uma caneca verde e outra amarela, simetria perfeita.",
    "maternidade": "mesa de escritório à noite com um par de sapatinhos de bebê ao lado do teclado, crachá virado e uma agenda fechada, luz amarela suave de luminária.",
    "indicadores": "vista aérea noturna de uma cidade brasileira média com bairros iluminados em amarelo e áreas verdes escuras, estradas como linhas de luz, sem placas legíveis.",
    "empresas": "fachadas de prédios corporativos de vidro à noite vistas de baixo, ao lado um pequeno comércio de rua iluminado, contraste entre grande e pequeno, reflexos verdes e amarelos.",
    "metodo": "mesa de analista à noite com dois monitores mostrando gráficos e tabelas abstratas sem texto legível, caderno, caneca, cidade desfocada pela janela.",
}

def chave():
    """Lê OPENAI_API_KEY do ambiente ou do arquivo .env na raiz do repositório."""
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    env = P / ".env"
    if env.exists():
        for l in env.read_text(encoding="utf-8").splitlines():
            if l.strip().startswith("OPENAI_API_KEY="):
                return l.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("Defina OPENAI_API_KEY (veja .env.example).")


def gera(nome):
    dst = IMG / f"{nome}.jpg"
    req = urllib.request.Request("https://api.openai.com/v1/images/generations",
        data=json.dumps({"model": MODELO, "prompt": ESTILO + CENAS[nome], "size": "1536x1024", "quality": "medium", "n": 1}).encode(),
        headers={"Authorization": "Bearer " + chave(), "Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=300).read())
        png = IMG / f"{nome}.png"
        png.write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
        if shutil.which("sips"):  # macOS: converte para JPEG 1400 px
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "78", "-Z", "1400", str(png), "--out", str(dst)], capture_output=True)
            png.unlink(missing_ok=True)
        else:  # outros sistemas: mantém o PNG
            return nome, f"ok ({png.name})"
        return nome, "ok"
    except Exception as e:
        msg = getattr(e, "read", lambda: b"")()[:200]
        return nome, f"falhou {type(e).__name__} {msg}"

if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    refazer = set(sys.argv[sys.argv.index("--refazer") + 1].split(",")) if "--refazer" in sys.argv else set()
    fila = [n for n in CENAS if n in refazer or not (IMG / f"{n}.jpg").exists()]
    print(len(fila), "imagens na fila", flush=True)
    with ThreadPoolExecutor(3) as ex:
        for n, st in ex.map(gera, fila):
            print(n, st, flush=True)
