# betting-recommender
A python framework which, based on data gathered from past games and bookmaker odds, can suggest bets to maximize profit. With current optimal settings, the betting recommender achieves a **48.8%** probability of long-term profits. The method by which this figure was estimated is the following:
  1) Data was gathered for a period of two months - both in terms of game outcomes and bookmaker odds. For the 12 leagues that the framework currently supports, this amounts to 952 football matches.
  2) For each bookmaker out of Bet365, Bwin and Coral, 500 individial simulations were made, where a simulation consists of randomly choosing what to bet on in each game. The test gains value from the fact that the amount to bet is *not* chosen randomly - it is calculated using the Kelly criterion, which bases its decision on the estimated probability of the event and the potential earnings from guessing correctly (i.e. also considers the bookmaker odds). Calculating the percentage of simulations that end up with a profit can effectively be used as a test for how good the probability estimation is (as the bookmaker odds are fixed). This is the method I used to compare probability estimators with different settings. It turns out, (at least as of publishing this) that the *BookieAverageProbabilityEstimator* has the highest success rate (the aforementioned 48.8%)

## Data Sources
  Central to the framework are data services. They hold data from past games in the competitions that the framework supports.
The abstraction of a *FootballDataService* exists, but as of now only has one concrete implementation in the *SoccerwayFootballDataService* which, as the name suggests, scrapes data from the website soccerway.com
  Currently, the Soccerway data service supports the following leagues:\
    1) English Premier League         
    2) English Championship               
    3) Italian Serie A                  
    4) Spanish La Liga                   
    5) German Bundesliga                  
    6) French Ligue 1                   
    7) Dutch Eredivisie  
    8) Portuguese Primeira Liga    
    9) Turkish Super Lig    
    10) Russian Premier League    
    11) Greek Super League    
    12) Scottish Premier League  
    
  In order to choose bets, the framework obviously needs odds given by real bookmakers. For this purpose, there are several implementations of *OddsProvider*, scraping odds from bet365.com, bwin.com, coral.co.uk and efbet.com
 
 ## Probability estimators
  There are two main ways to go about estimating the outcome of a match - deterministic and stochastic. With the deterministic approach, the framework would take some data from the data services and/or odds providers and spit out a forecast. However, this method woud not be very flexible and would not give any hints as to how confident the framework is in its estimation.
  Given the disadvantages of a deterministic approach, I chose to pursue probabilistic methods. The framework contains three types of probability estimators:\
    1) ***RnnProbabilityEstimator*** - Uses several pretrained recurrent neural networks (one modeling first half, one second half and one modeling final outcomes as a whole). Each neural network models the mean of a Poisson distribution, which is then used to make probability estimations for the upcoming game.\
    2) ***EloRatingsProbabilityEstimator*** - Estimator based on the popular Elo ratings system, which was initially invented for predicting chess, but later adapted for various games, including football. Makes a couple of additions to the standard Elo ratings model, most notably adding home and away form estimations for each team, scaling the post-game points change based on the actual goals margin in the game versus the expected margin (given the pre-game points difference between the teams) and using a per-league estimate of the average home/away advantage (whereas most other Elo models tend to use a fixed home advantage which is the same in every league). Spoiler alert: there is not a single league where playing away is an advantage. Probabilities are estimated by taking the pre-game points difference between the teams and looking up ata from past games with similar difference in strength(points) and taking the percentage of occurrence of various events as probabilities for the upcoming game.\
    3) ***BookieAverageProbabilityEstimator*** - The simplest yet the most effective estimator (at least as of date of current upload). Takes the odds from several bookmakers, converts them to probabilities and takes the average. The idea is to remove potential biases that each bookie may have (whether intentional or not) and arrive at a more realistic probability estimation than what the odds of a single bookie may suggest. Another advantage is that the framework's bet pickers are then naturally set up to take advantage of the bookies' biases when choosing a bet.
    
  The relations between the different components are summarized with the illustration below:
  
  
![Component Relations](/images/component-relations.jpg)
