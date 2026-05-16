/**
 * Leviathan Contracts Deployment Script
 *
 * Deploys the full Leviathan governance stack:
 * 1. LeviathanForwarder - ERC2771 forwarder for meta-transactions
 * 2. LeviathanToken - ERC20Votes governance token
 * 3. LeviathanGovernor - Governance contract with gasless voting support
 *
 * Usage:
 *   # Local hardhat network
 *   npx hardhat run scripts/deploy.js
 *
 *   # Avalanche Fuji testnet
 *   npx hardhat run scripts/deploy.js --network fuji
 *
 * Prerequisites:
 *   1. Set PRIVATE_KEY in .env file
 *   2. Ensure account has AVAX for gas (get from faucet for testnet)
 */

const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();

  console.log("=".repeat(60));
  console.log("Leviathan Contracts Deployment");
  console.log("=".repeat(60));
  console.log();
  console.log(`Network: ${hre.network.name}`);
  console.log(`Chain ID: ${(await hre.ethers.provider.getNetwork()).chainId}`);
  console.log(`Deployer: ${deployer.address}`);

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`Balance: ${hre.ethers.formatEther(balance)} AVAX/ETH`);
  console.log();

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
  console.log(`   Voting Delay: ${votingDelay} blocks (~${Number(votingDelay) / 7200} days @ 12s/block)`);
  console.log(`   Voting Period: ${votingPeriod} blocks (~${Number(votingPeriod) / 7200} days @ 12s/block)`);

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

  // Output for config.yaml
  console.log("Add to config.yaml:");
  console.log("```yaml");
  console.log("chain:");
  console.log("  type: evm");
  console.log(`  chain_id: ${(await hre.ethers.provider.getNetwork()).chainId}`);
  console.log(`  rpc_url: ${hre.network.config.url || "http://127.0.0.1:8545"}`);
  console.log(`  governor_address: "${governorAddress}"`);
  console.log(`  token_address: "${tokenAddress}"`);
  console.log(`  forwarder_address: "${forwarderAddress}"`);
  console.log("```");
  console.log();

  // Delegate tokens to self for voting power
  console.log("4. Delegating tokens to deployer for voting power...");
  const delegateTx = await token.delegate(deployer.address);
  await delegateTx.wait();
  const votingPower = await token.getVotes(deployer.address);
  console.log(`   Voting power: ${hre.ethers.formatEther(votingPower)} Leviathan`);

  console.log();
  console.log("Deployment complete!");
  console.log();

  // Next steps
  console.log("Next Steps:");
  console.log("1. Update config.yaml with the contract addresses above");
  console.log("2. Distribute tokens to test voters");
  console.log("3. Have voters delegate their tokens (token.delegate(voterAddress))");
  console.log("4. Create a test proposal via LeviathanGovernor");
  console.log("5. Test gasless voting via Leviathan Observer Mode");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
