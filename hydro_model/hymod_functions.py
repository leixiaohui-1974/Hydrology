import numpy as np
import math

def Pdm01(Hpar, Bpar, Hbeg, PP, PET):
        b = math.log(1-Bpar/2)/math.log(0.5)
        Cpar = Hpar/(1+b)
        Cbeg = Cpar*(1-(1-Hbeg/Hpar)**(1+b))

        OV2 = max(PP+Hbeg-Hpar, 0)
        PPinf = PP-OV2

        Hint = min((PPinf+Hbeg), Hpar)
        Cint = Cpar*(1-(1-Hint/Hpar)**(1+b))
        OV1 = max(PPinf+Cbeg-Cint, 0)

        OV = OV1+OV2
        ET = min(PET, Cint)
        Cend = Cint-ET
        Hend = Hpar*(1-(1-Cend/Cpar)**(1/(1+b)))

        return OV, ET, Hend, Cend

def Nash(K, N, Xbeg, Inp):
        OO = np.zeros(N)
        Xend = np.zeros(N)
        for Res in range(0,N):
                OO[Res] = K*Xbeg[Res]
                Xend[Res] = Xbeg[Res]-OO[Res]

                if Res == 0:
                        Xend[Res] = Xend[Res] + Inp
                else:
                        Xend[Res] = Xend[Res] + OO[Res-1]

        out = OO[N-1]
        return out, Xend
