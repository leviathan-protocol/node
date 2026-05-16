/**
 * Leviathan Contracts Deployment Script - Leviathan Subnet
 *
 * Deploys the full Leviathan governance stack to the local Leviathan Subnet:
 * 1. LeviathanForwarder - ERC2771 forwarder for meta-transactions
 * 2. LeviathanToken - ERC20Votes governance token
 * 3. LeviathanGovernor - Governance contract with gasless voting support
 *
 * Usage:
 *   # First, start the Leviathan Subnet
 *   ./scripts/setup_leviathan_subnet.sh
 *
 *   # Then deploy contracts
 *   npx hardhat run scripts/deploy_subnet.js --network leviathanSubnet
 *
 * The EWOQ test account is pre-funded with 1M Leviathan native tokens for gas.
 */

const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await hre.ethers.getSigners();

  console.log("=".repeat(60));
  console.log("Leviathan Contracts Deployment - Leviathan Subnet");
  console.log("=".repeat(60));
  console.log();
  console.log(`Network: ${hre.network.name}`);
  console.log(`Chain ID: ${(await hre.ethers.provider.getNetwork()).chainId}`);
  console.log(`Deployer: ${deployer.address}`);

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`Balance: ${hre.ethers.formatEther(balance)} Leviathan`);
  console.log();

  if (balance === 0n) {
    console.error("ERROR: Deployer has no balance!");
    console.error("Make sure the Leviathan Subnet is running:");
    console.error("  ./scripts/setup_leviathan_subnet.sh");
    process.exit(1);
  }

  // 1. Deploy LeviathanForwarder
  console.log("1. Deploying LeviathanForwarder...");
  const LeviathanForwarder = await hre.ethers.getContractFactory("LeviathanForwarder");
  const forwarder = await LeviathanForwarder.deploy();
  await forwarder.waitForDeployment();
  const forwarderAddress = await forwarder.getAddress();
  console.log(`   LeviathanForwarder deployed to: ${forwarderAddress}`);

  // 2. Deploy LeviathanToken
  console.log("2. Deploying LeviathanToken...");
  const LeviathanToken = await hre.ethers.getContractFactory("LeviathanToken");
  const token = await LeviathanToken.deploy(deployer.address);
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log(`   LeviathanToken deployed to: ${tokenAddress}`);

  // Verify token details
  const tokenName = await token.name();
  const tokenSymbol = await token.symbol();
  const totalSupply = await token.totalSupply();
  console.log(`   Token: ${tokenName} (${tokenSymbol})`);
  console.log(`   Total Supply: ${hre.ethers.formatEther(totalSupply)} Leviathan`);

  // 3. Deploy LeviathanGovernor
  console.log("3. Deploying LeviathanGovernor...");
  const LeviathanGovernor = await hre.ethers.getContractFactory("LeviathanGovernor");
  const governor = await LeviathanGovernor.deploy(tokenAddress, forwarderAddress);
  await governor.waitForDeployment();
  const governorAddress = await governor.getAddress();
  console.log(`   LeviathanGovernor deployed to: ${governorAddress}`);

  // Verify governor settings
  const votingDelay = await governor.votingDelay();
  const votingPeriod = await governor.votingPeriod();
  console.log(`   Voting Delay: ${votingDelay} seconds (~${Number(votingDelay) / 86400} days)`);
  console.log(`   Voting Period: ${votingPeriod} seconds (~${Number(votingPeriod) / 86400} days)`);

  // 4. Delegate tokens to deployer for voting power
  console.log("4. Delegating tokens to deployer for voting power...");
  const delegateTx = await token.delegate(deployer.address);
  await delegateTx.wait();
  const votingPower = await token.getVotes(deployer.address);
  console.log(`   Voting power: ${hre.ethers.formatEther(votingPower)} Leviathan`);

  // Summary
  console.log();
  console.log("=".repeat(60));
  console.log("Deployment Summary");
  console.log("=".repeat(60));
  console.log();
  console.log("Contract Addresses:");
  console.log(`  LeviathanForwarder: ${forwarderAddress}`);
  console.log(`  LeviathanToken:     ${tokenAddress}`);
  console.log(`  LeviathanGovernor:  ${governorAddress}`);
  console.log();

  // Generate config for Python sidecar
  const chainId = (await hre.ethers.provider.getNetwork()).chainId;
  const rpcUrl = hre.network.config.url;

  const configYaml = `# Leviathan Subnet Configuration (Auto-generated)
# Generated at: ${new Date().toISOString()}
#
# Start subnet first: ./scripts/setup_leviathan_subnet.sh

chain:
  type: evm
  chain_id: "${chainId}"
  rpc_url: "${rpcUrl}"
  governor_address: "${governorAddress}"
  token_address: "${tokenAddress}"
  forwarder_address: "${forwarderAddress}"
  gas_limit: 200000

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"
  n_ctx: 8192

sidecar:
  poll_interval_seconds: 60
  max_retries: 3
  state_file: "sidecar_state.json"
  decisions_log: "decisions.log"

# Environment variables needed:
#   RELAYER_PRIVATE_KEY=56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027
`;

  // Write config file
  const configPath = path.join(__dirname, "..", "..", "config_leviathan_subnet.yaml");
  fs.writeFileSync(configPath, configYaml);
  console.log(`Config written to: ${configPath}`);
  console.log();

  // Output usage instructions
  console.log("=".repeat(60));
  console.log("Ready to Use!");
  console.log("=".repeat(60));
  console.log();
  console.log("Set relayer private key (EWOQ test key):");
  console.log("  export RELAYER_PRIVATE_KEY=56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027");
  console.log();
  console.log("Start Observer Mode:");
  console.log("  python main.py --mode observer --config config_leviathan_subnet.yaml");
  console.log();
  console.log("Test connection:");
  console.log(`  curl ${rpcUrl} -X POST -H "Content-Type: application/json" --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}'`);
  console.log();

  // Also write a JSON file for programmatic access
  const deploymentInfo = {
    network: hre.network.name,
    chainId: chainId.toString(),
    rpcUrl: rpcUrl,
    deployer: deployer.address,
    contracts: {
      forwarder: forwarderAddress,
      token: tokenAddress,
      governor: governorAddress,
    },
    deployedAt: new Date().toISOString(),
  };

  const deploymentPath = path.join(__dirname, "..", "deployments", "leviathan_subnet.json");
  fs.mkdirSync(path.dirname(deploymentPath), { recursive: true });
  fs.writeFileSync(deploymentPath, JSON.stringify(deploymentInfo, null, 2));
  console.log(`Deployment info saved to: ${deploymentPath}`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
