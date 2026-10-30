// Known Ethereum exchange hot/withdrawal wallets — the addresses that fund retail wallets when they
// "withdraw to self-custody". Used by the ETH-funding enrichment: a wallet funded by one of these is
// tagged with the venue, but a SHARED exchange funder NEVER links two wallets (millions withdraw from
// the same hot wallet). Only a shared PRIVATE (unlabelled) funder is treated as a coordination edge.
// Lowercased. Not exhaustive — extend as new funders surface; anything unmatched is treated as private.
export const ETH_LABELS = {
  // Coinbase
  "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
  "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
  "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740": "Coinbase",
  "0x3cd751e6b0078be393132286c442345e5dc49699": "Coinbase",
  "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511": "Coinbase",
  "0xeb2629a2734e272bcc07bda959863f316f4bd4cf": "Coinbase",
  "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "Coinbase",
  "0x6b76f8b1e9e59913bfe758821887311ba1805cab": "Coinbase",
  "0xf6874c88757721a02f47592140905c4336dfbc61": "Coinbase",
  "0x881d4032abe4188e2237efcd27ab435e81fc6bb1": "Coinbase",
  "0x02466e547bfdab679fc49e96bbfc62b9747d997c": "Coinbase",
  // Binance
  "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
  "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
  "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
  "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance",
  "0x9696f59e4d72e237be84ffd425dcad154bf96976": "Binance",
  "0x4976a4a02f38326660d17bf34b431dc6e2eb2327": "Binance",
  "0x4e9ce36e442e55ecd9025b9a6e0d88485d628a67": "Binance",
  "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": "Binance",
  "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance",
  "0x5a52e96bacdabb82fd05763e25335261b270efcb": "Binance",
  // Kraken
  "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
  "0xa83b11093c858c86321fbc4c20fe82cdbd58e09e": "Kraken",
  "0xe853c56864a2ebe4576a807d26fdc4a0ada51919": "Kraken",
  "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": "Kraken",
  "0xfa52274dd61e1643d2205169732f29114bc240b3": "Kraken",
  // ── Kraken cold/hot + funding wallets (owner-identified 2026-08-30, after a false "ALTHEA coordination"
  //    positive — these had been swept into the operator cohort as "whales" and the funder created FAKE
  //    shared-funder edges). A shared exchange funder never links wallets, so labelling 0xf30ba13e here
  //    dissolves the false cluster.
  "0x7dafba1d69f6c01ae7567ffd7b046ca03b706f83": "Kraken",
  "0xd2dd7b597fd2435b6db61ddf48544fd931e6869f": "Kraken",
  "0xc2e6cc2b4942fd803ed5a6e8e3b4890503d12645": "Kraken",
  "0x504ce9e51e508c85a161058c12e970a903d482fc": "Kraken",
  "0xf30ba13e4b04ce5dc4d254ae5fa95477800f0eb0": "Kraken",
  // OKX
  "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
  "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3": "OKX",
  "0xa7efae728d2936e78bda97dc267687568dd593f3": "OKX",
  "0x5041ed759dd4afc3a72b8192c143f72f4724081a": "OKX",
  // Bybit
  "0xf89d7b9c864f589bbf53a82105107622b35eaa40": "Bybit",
  "0xee5b5b923ffce93a870b3104b7ca09c3db80047a": "Bybit",
  // Gate.io
  "0x0d0707963952f2fba59dd06f2b425ace40b492fe": "Gate.io",
  "0x1c4b70a3968436b9a0a9cf5205c787eb81bb558c": "Gate.io",
  // KuCoin
  "0x689c56aef474df92d44a1b70850f808488f9769c": "KuCoin",
  "0xd6216fc19db775df9774a6e33526131da7d19a2c": "KuCoin",
  // Crypto.com
  "0x6262998ced04146fa42253a5c0af90ca02dfd2a3": "Crypto.com",
  "0x46340b20830761efd32832a74d7169b29feb9758": "Crypto.com",
  // Huobi / HTX
  "0xab5c66752a9e8167967685f1450532fb96d5d24f": "HTX",
  "0xe93381fb4c4f14bda253907b18fad305d799241a": "HTX",
  "0xdc76cd25977e0a5ae17155770273ad58648900d3": "HTX",
  // Robinhood
  "0x40b38765696e3d5d8d9d834d8aad4bb6e418e489": "Robinhood",
  // MEXC (also a pepecoin EXCLUDE label)
  "0x9642b23ed1e01df1092b92641051881a322f5d4e": "MEXC",
  "0x0211f3cedbef3143223d3acf0e589747933e8527": "MEXC",
};

export const labelFunder = (addr) => (addr ? ETH_LABELS[addr.toLowerCase()] || null : null);
export const isExchange = (addr) => !!labelFunder(addr);
