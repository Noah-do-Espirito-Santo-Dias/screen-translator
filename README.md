# Tradutor de Tela para Visual Novels (EN -> PT)

Um tradutor de tela leve, rápido e 100% offline projetado especificamente para Visual Novels e jogos em modo janela/sem borda no Windows. 

O programa captura apenas a caixa de texto do jogo, aplica OCR local para reconhecer o texto em inglês e exibe a tradução em português em uma camada (*overlay*) sobreposta ao jogo, sem interferir no clique do mouse.

---

## 🚀 Recursos principais

- **100% Offline e Sem Limite de Requisições:** Utiliza o motor de IA local **ArgosTranslate**, eliminando bloqueios de IP (erros HTTP 429/403) comuns em serviços online.
- **OCR Local de Alta Performance:** Leitura de imagem ultra-rápida via **RapidOCR** (ONNX Runtime).
- **Overlay Transparente e Pass-Through:** A interface de tradução permite que os cliques do mouse passem direto para o jogo.
- **Invisível para a Captura de Tela:** Utiliza APIs nativas do Windows (`WDA_EXCLUDEFROMCAPTURE`) para evitar que a própria overlay de tradução seja lida pelo OCR.
- **Detecção de Mudança Estável:** Captura inteligente que espera a animação de digitação do texto estabilizar antes de rodar a tradução, economizando CPU.
- **Cache Inteligente com Normalização:** Ignora variações sutis e ruídos visuais no OCR para evitar processamento desnecessário.
- **Ajuste Automático de Fonte:** Ajusta dinamicamente o tamanho do texto para garantir que ele caiba dentro da região selecionada.

---

## 📋 Pré-requisitos

- **Sistema Operacional:** Windows 10 (versão 2004 ou mais recente) ou Windows 11.
- **Python:** Versão 3.10 ou superior instalada.
- **Modo de Exibição do Jogo:** O jogo deve rodar em **Modo Janela** ou **Janela Sem Bordas** (*Borderless Windowed*).

---

## 🛠️ Instalação

1. **Clone ou baixe este repositório**

2. **Crie e ative um ambiente virtual (recomendado):**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

> **Nota:** Na primeira execução, o programa baixará automaticamente o modelo de tradução de Inglês para Português (~150 MB). Aguarde alguns instantes até que o modelo seja carregado na memória.

---

## 🎮 Como Usar

1. Inicie o script Python:
   ```bash
   python tradutor_tela.py
   ```
2. Abra o seu jogo em modo janela ou tela cheia sem borda.
3. Pressione **`F9`** (ou clique no botão **"Selecionar área"** do painel de controle).
4. Clique e arraste um retângulo vermelho sobre a **caixa de texto do jogo**.
5. Pronto! A tradução aparecerá automaticamente sobreposta à caixa de texto.

### 🎹 Atalhos Globais

| Atalho | Ação |
| :---: | :--- |
| **`F8`** | Pausa / Retoma a captura e a exibição da overlay |
| **`F9`** | Inicia a seleção da área de leitura da tela |
| **`F10`** | Encerra o aplicativo com segurança |

---

## ⚙️ Personalização (Configurações)

Você pode personalizar o comportamento e a aparência da overlay editando as constantes no topo do arquivo `tradutor_tela.py`:

```python
# ----------------------------- CONFIGURAÇÕES -----------------------------
INTERVALO = 0.25          # Segundos entre capturas (valores maiores usam menos CPU)
FRAMES_ESTAVEIS = 2       # Frames idênticos necessários antes de acionar o OCR
MIN_CONFIANCA = 0.55      # Confiança mínima do OCR para considerar uma linha válida
COR_FUNDO = "#14141c"     # Cor da caixa de fundo (use transparente se configurado)
COR_TEXTO = "#ffffff"     # Cor da fonte da tradução (código Hexadecimal)
FONTE = "Segoe UI"        # Família da fonte utilizada na overlay
TAM_MAX, TAM_MIN = 40, 10 # Limites de tamanho de fonte em pixels
OPACIDADE = 0.97          # Opacidade da janela overlay (0.1 a 1.0)
# --------------------------------------------------------------------------
```


## 🧩 Estrutura do Projeto

```text
├── tradutor_tela.py   # Script principal do tradutor e interface gráfica
├── regiao.json        # Arquivo gerado automaticamente com a última área demarcada
├── requirements.txt   # Dependências do projeto (RapidOCR, ArgosTranslate, MSS, etc.)
└── README.md          # Documentação do projeto
```

---

## 🛡️ Licença

Este projeto é de código aberto e distribuído para fins educacionais e de entretenimento. Sinta-se à vontade para modificar e contribuir!

## 🛠️ Desenvolvimento e Créditos
Projeto concebido, arquitetado e revisado por **Noah Dias**, utilizando assistentes de IA no desenvolvimento e prototipagem de código.