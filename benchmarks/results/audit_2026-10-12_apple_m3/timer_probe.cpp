#include <chrono>
#include <cstdio>
#include <vector>
#include <algorithm>
int main(){
  using C=std::chrono::steady_clock;
  const int N=1000000; std::vector<long long> d(N);
  for(int i=0;i<N;++i){auto a=C::now();auto b=C::now();d[i]=std::chrono::duration_cast<std::chrono::nanoseconds>(b-a).count();}
  std::sort(d.begin(),d.end());
  long long mn=d[0]; long long nz=0; for(auto x:d) if(x>0){nz=x;break;}
  std::printf("back_to_back_now_ns: min=%lld smallest_nonzero=%lld p50=%lld p99=%lld\n",mn,nz,d[N/2],d[N*99/100]);
  auto t0=C::now(); for(int i=0;i<N;++i){volatile auto x=C::now(); (void)x;} auto t1=C::now();
  std::printf("mean_cost_per_now_call_ns=%.2f\n", std::chrono::duration<double,std::nano>(t1-t0).count()/N);
  std::printf("steady_clock_period_num_den=%lld/%lld\n",(long long)C::period::num,(long long)C::period::den);
}
