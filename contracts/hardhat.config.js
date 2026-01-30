require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      evmVersion: "cancun",
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  networks: {
    // Local development
    hardhat: {
      chainId: 31337,
    },
    localhost: {
      url: "http://127.0.0.1:8545",
    },
    // DAHAO Subnet (Local Avalanche L1)
    // Start with: ./scripts/setup_dahao_subnet.sh
    // Note: RPC URL includes the blockchain hash assigned at deployment
    dahaoSubnet: {
      url: process.env.DAHAO_RPC_URL || "http://127.0.0.1:9654/ext/bc/2QfrnBRib5ZfJac5vNc6gTSHsvNtPnwhxF5GEwNFZMbariKTVT/rpc",
      chainId: 43210,
      // EWOQ test key - pre-funded with 1M tokens (DO NOT USE IN PRODUCTION)
      accounts: ["56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027"],
    },
    // Avalanche Fuji Testnet
    fuji: {
      url: process.env.FUJI_RPC_URL || "https://api.avax-test.network/ext/bc/C/rpc",
      chainId: 43113,
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
    },
    // Avalanche Mainnet (for future use)
    avalanche: {
      url: process.env.AVAX_RPC_URL || "https://api.avax.network/ext/bc/C/rpc",
      chainId: 43114,
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
    },
  },
  etherscan: {
    // Snowtrace API key for contract verification
    apiKey: {
      avalancheFujiTestnet: process.env.SNOWTRACE_API_KEY || "",
      avalanche: process.env.SNOWTRACE_API_KEY || "",
    },
  },
  paths: {
    sources: "./src",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
};
